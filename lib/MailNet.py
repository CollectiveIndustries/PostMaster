import tensorflow as tf
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.models import Sequential, load_model  # type: ignore
from tensorflow.keras.layers import Dense, Embedding, LSTM, Dropout, Input # type: ignore
from tensorflow.keras.preprocessing.text import Tokenizer # type: ignore
from tensorflow.keras.preprocessing.sequence import pad_sequences # type: ignore
import pickle
import logging
import os
import threading
from .post import Email, extract_email_data
from .config import config

class MailNet():
    def __init__(self, max_vocab_size=10000):
        self.max_vocab_size = max_vocab_size
        self.tokenizer = Tokenizer(num_words=self.max_vocab_size, oov_token="<OOV>")
        self.max_sequence_length = 300
        self.model_lock = threading.RLock()
        self.model = None

    def save_history(self):
        """Save training history."""
        with open(f"{config.TRAINING_DATA_PATH}/history.pkl", "wb") as f:
            pickle.dump(self.model.history.history, f)

    def preprocess_data(self, texts: list):
        """Preprocess email texts into padded sequences."""
        # Ensure texts is not empty
        if not texts:
            logging.error("No texts to preprocess.")
            raise ValueError("Input texts list is empty.")

        # Debug: check the first few texts
        logging.debug(f"Preprocessing {len(texts)} texts: {texts[:3]}")

        # Convert texts to sequences
        sequences = self.tokenizer.texts_to_sequences(texts)
        
        # Check if sequences are empty or invalid
        if not sequences or all(len(seq) == 0 for seq in sequences):
            logging.error("Text processing failed. Sequences are empty or invalid.")
            raise ValueError("Tokenization failed. Sequences are empty.")

        # Pad sequences to a consistent length
        padded_sequences = pad_sequences(sequences, maxlen=self.max_sequence_length, padding='post', truncating='post')

        # Debug: check the first few padded sequences
        logging.debug(f"First 3 padded sequences: {padded_sequences[:3]}")
        
        return padded_sequences

    def fit_tokenizer(self, email_lst: list[Email]) -> None:
        """Fit or update the tokenizer on the provided list of emails."""
        texts = [extract_email_data(email) for email in email_lst]
    
        # Log current word index size
        current_vocab_size = len(self.tokenizer.word_index)
        logging.debug(f"Current tokenizer vocabulary size: {current_vocab_size}")
    
        # Fit or update the tokenizer with new texts
        self.tokenizer.fit_on_texts(texts)
    
        # Log updated word index size
        new_vocab_size = len(self.tokenizer.word_index)
        logging.debug(f"Updated tokenizer vocabulary size: {new_vocab_size}")
    
        if new_vocab_size > current_vocab_size:
            logging.info(f"Tokenizer expanded: Added {new_vocab_size - current_vocab_size} new words.")
        else:
            logging.info("No new words were added to the tokenizer vocabulary.")
    

    def train(self, email_lst: list[Email], labels: list[int], epochs: int = 50, batch_size: int = 64) -> None:
        """Train the spam filter model."""
        with self.model_lock:
            # Fit the tokenizer only if it's not already fitted
            if not self.tokenizer.word_index:  # Check if tokenizer has already been fitted
                self.fit_tokenizer(email_lst)
            
            # Filter out emails with None attributes and adjust the labels accordingly
            valid_data = [
                (email, label) for email, label in zip(email_lst, labels)
                if all(getattr(email, attr, None) is not None for attr in ['subject', 'sender', 'recipient', 'payload'])
            ]

            # Unpack filtered emails and labels
            if not valid_data:
                logging.warning("No valid emails found for training. Skipping training process.")
                return

            email_lst, labels = zip(*valid_data)  # Unpack back into separate lists

            # Prepare text data and labels
            text = [extract_email_data(email) for email in email_lst]
            X = self.preprocess_data(text)
            y = tf.convert_to_tensor(labels)

            # Model definition (define once)
            if self.model is None:  # Only create a model if it doesn't already exist
                self.model = Sequential([
                    Input(shape=(self.max_sequence_length,)),
                    Embedding(self.max_vocab_size, 128),
                    LSTM(64, return_sequences=False),
                    Dropout(0.3),
                    Dense(1, activation='sigmoid')
                ])

                self.model.compile(optimizer=Adam(), loss='binary_crossentropy', metrics=['accuracy'])

            # Training with early stopping
            early_stopping = tf.keras.callbacks.EarlyStopping(
                monitor='val_loss', patience=3, restore_best_weights=True
            )
            self.model.fit(
                X, y,
                epochs=epochs,
                batch_size=batch_size,
                validation_split=0.2,
                callbacks=[early_stopping]
            )

    def classify(self, email: Email) -> int:
        """Classify email as spam or ham (0 or 1)."""
        with self.model_lock:
            if not self.model:
                logging.error("Model is not trained or loaded. Please train or load a model before classification.")
                raise ValueError("Model is not trained or loaded. Please train or load a model before classification.")
            email_text = extract_email_data(email)
            X = self.preprocess_data([email_text])
            predictions = self.model.predict(X)
            return 1 if predictions[0] > 0.5 else 0

    def save_model(self, model_path=f"{config.TRAINING_DATA_PATH}/SpamVanquisher_TensorFlow.keras"):
        """Save the trained model to disk."""
        if not self.model:
            logging.error("No model found to save.")
            raise ValueError("No model found to save.")
        self.model.save(model_path)
        logging.info("Trained model saved to disk")

    def load_model(self, model_path=f"{config.TRAINING_DATA_PATH}/SpamVanquisher_TensorFlow.keras"):
        """Load a saved model from disk or create a new one if it doesn't exist."""
        if os.path.exists(model_path):
            logging.info(f"Loading model from '{model_path}'")
            self.model = load_model(model_path)
        else:
            logging.warning(f"Model file '{model_path}' not found. Creating a new model.")
            self.model = self._create_model()
            self.model.save(model_path)
            logging.info(f"New model created and saved to '{model_path}'")

    def _create_model(self):
        """Define and return a new TensorFlow model."""
        model = Sequential([
            Input(shape=(self.max_sequence_length,)),  # Define the input shape clearly
            Dense(128, activation='relu'),
            Dense(64, activation='relu'),
            Dense(1, activation='sigmoid')  # For binary classification
        ])
        model.compile(optimizer=Adam(), loss='binary_crossentropy', metrics=['accuracy'])
        return model

    def unload_model(self):
        """Unload the model and release resources."""
        if self.model is not None:
            logging.info("Unloading model and clearing resources.")
            self.model = None  # Remove Python reference
            from keras import backend as K
            K.clear_session()  # Clear TensorFlow backend session
            import gc
            gc.collect()       # Trigger garbage collection
            logging.info("Model unloaded successfully.")
        else:
            logging.warning("No model is loaded to unload.")
