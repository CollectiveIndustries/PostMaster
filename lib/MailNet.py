import tensorflow as tf
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.models import Sequential, load_model # type: ignore
from tensorflow.keras.layers import Dense, Embedding, LSTM, Dropout, Input # type: ignore
from tensorflow.keras.preprocessing.text import Tokenizer # type: ignore
from tensorflow.keras.preprocessing.sequence import pad_sequences # type: ignore
import logging
import os
import threading
from .config import config
from .post import Email, extract_email_data
class MailNet():
    def __init__(self, max_vocab_size=10000):
        self.max_vocab_size = max_vocab_size
        self.tokenizer = Tokenizer(num_words=self.max_vocab_size, oov_token="<OOV>")
        self.max_sequence_length = 300
        self.model_lock = threading.RLock()
        self.model = None

    def preprocess_data(self, texts: list):
        """Preprocess email texts into padded sequences."""

        sequences = self.tokenizer.texts_to_sequences(texts)

        return pad_sequences(sequences, maxlen=self.max_sequence_length, padding='post', truncating='post')

    def train(self, email_text, labels, epochs=50, batch_size=64):
        """Train the spam filter model."""
        with self.model_lock:
            early_stopping = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=3, restore_best_weights=True)

            text = [ extract_email_data(email) for email in email_text]

            # Tokenizer fit
            self.tokenizer.fit_on_texts(text)
            X = self.preprocess_data(text)
            y = tf.convert_to_tensor(labels)

            # Model definition
            self.model = Sequential([
                Input(shape=(self.max_sequence_length,)),  # or just use input_length in Embedding layer
                Embedding(self.max_vocab_size, 128),
                LSTM(64, return_sequences=False),
                Dropout(0.3),
                Dense(1, activation='sigmoid')
            ])

            self.model.compile(optimizer=Adam(), loss='binary_crossentropy', metrics=['accuracy'])

            # Training
            self.model.fit(X, y, epochs=epochs, batch_size=batch_size, validation_split=0.2, callbacks=[early_stopping])

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
            logging.info(f"Loading model from {model_path}")
            self.model = load_model(model_path)
        else:
            logging.warning(f"Model file {model_path} not found. Creating a new model.")
            self.model = self._create_model()
            self.model.save(model_path)
            logging.info(f"New model created and saved to {model_path}")

    def _create_model(self):
        """Define and return a new TensorFlow model."""
        # Model definition
        model = Sequential([
            Input(shape=(self.max_sequence_length,)),  # Define the input shape clearly
            Dense(128, activation='relu'),
            Dense(64, activation='relu'),
            Dense(1, activation='sigmoid')  # For binary classification
        ])
        model.compile(optimizer=Adam(), loss='binary_crossentropy', metrics=['accuracy'])
        return model
