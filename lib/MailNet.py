import logging
import os
import pickle
import threading

import tensorflow as tf
from tensorflow.keras.layers import LSTM, Dense, Dropout, Embedding, Input
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.preprocessing.text import Tokenizer

from .config import config
from .post import Email


class MailNet:
    def __init__(self, max_vocab_size: int = 10000, max_sequence_length: int = 300) -> None:
        self.max_vocab_size = max_vocab_size
        self.max_sequence_length = max_sequence_length
        self.tokenizer = Tokenizer(num_words=self.max_vocab_size, oov_token="<OOV>")
        self.model_lock = threading.RLock()
        self.vocab_size = 0
        self.model = None

    def save_history(self) -> None:
        """Save the training history."""
        if hasattr(self.model, "history") and self.model.history:
            history_path = f"{config.TRAINING_DATA_PATH}/history.pkl"
            with open(history_path, "wb") as f:
                pickle.dump(self.model.history.history, f)
            logging.info(
                f"Training history saved to '{history_path}'"
            )
        else:
            logging.warning("No training history found to save.")

    def preprocess_data(self, texts: list):
        """Preprocess email texts into padded sequences."""
        if not texts:
            raise ValueError("Input texts list is empty.")
        logging.debug(
            f"Preprocessing {len(texts)} texts."
        )
        sequences = self.tokenizer.texts_to_sequences(texts)
        if not sequences or all(len(seq) == 0 for seq in sequences):
            raise ValueError("Tokenization failed. Sequences are empty.")
        padded_sequences = pad_sequences(sequences, maxlen=self.max_sequence_length, padding='post', truncating='post')
        logging.debug(
            f"First 3 padded sequences: {padded_sequences[:3]}"
        )
        return padded_sequences

    def fit_tokenizer(self, email_texts: list):
        """Fit or update the tokenizer on the provided list of email texts."""
        current_vocab_size = len(self.tokenizer.word_index)
        self.tokenizer.fit_on_texts(email_texts)
        new_vocab_size = len(self.tokenizer.word_index)
        self.vocab_size = new_vocab_size + 1
        if new_vocab_size > current_vocab_size:
            logging.info(
                f"Tokenizer updated: Added {new_vocab_size - current_vocab_size} new words."
            )
        else:
            logging.info("Tokenizer vocabulary remains unchanged.")

    def train(self, email_lst: list, labels: list[int], epochs: int = 50, batch_size: int = 64):
        """Train the spam filter model."""
        logging.info(f"Starting training with {len(email_lst)} emails")
        with self.model_lock:
            if not self.tokenizer.word_index:
                logging.debug("Initializing tokenizer from training data")
                self.fit_tokenizer(email_lst)
            valid_data = [
                (email, label)
                for email, label in zip(email_lst, labels)
                if all(getattr(email, attr, None) for attr in ['subject', 'sender', 'recipient', 'payload'])
            ]
            if not valid_data:
                logging.warning("No valid emails for training. Skipping training.")
                return
            email_lst, labels = zip(*valid_data)
            text = [email.text() for email in email_lst]
            X = self.preprocess_data(text)
            y = tf.convert_to_tensor(labels)

            if self.model is None:
                self.model = self._create_model()
            early_stopping = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=3, restore_best_weights=True)
            self.model.fit(X, y, epochs=epochs, batch_size=batch_size, validation_split=0.2, callbacks=[early_stopping])

    def classify_emails(self, emails: list[Email]) -> None:
        """
        Classify a list of Email objects as spam (1) or ham (0) and update their class_id attribute.
        """
        logging.info(f"Classifying {len(emails)} emails")
        with self.model_lock:
            if not self.model:
                logging.error("Classification attempt with untrained model")
                raise ValueError("Model is not trained or loaded.")

            # Preprocess data for all emails
            email_texts = [email.text() for email in emails]
            X = self.preprocess_data(email_texts)

            # Debug: Check preprocessed data
            logging.debug(
                f"Preprocessed data sample: {X[:5]}"
            )

            # Predict classifications
            predictions = self.model.predict(X)

            # Debug: Check predictions
            logging.debug(
                f"Predictions: {predictions[:10]}"
            )

            # Update class_id for each email
            for email, prediction in zip(emails, predictions):
                email.class_id = 1 if prediction > 0.5 else 0
                logging.debug(
                    f"Email: {email.text()}, Prediction: {prediction}, Class ID: {email.class_id}"
                )

    def save_model(self, model_path: str = f"{config.TRAINING_DATA_PATH}/SpamVanquisher_TensorFlow.keras") -> None:
        """Save the model and tokenizer to disk."""
        if not self.model:
            raise ValueError("No model found to save.")
        self.model.save(model_path)
        logging.info(
            f"Model saved to '{model_path}'"
        )
        tokenizer_path = f"{config.TRAINING_DATA_PATH}/tokenizer.pkl"
        with open(tokenizer_path, "wb") as f:
            pickle.dump(self.tokenizer, f)
        logging.info(
            f"Tokenizer saved to '{tokenizer_path}'"
        )

    def load_model(self, model_path: str = f"{config.TRAINING_DATA_PATH}/SpamVanquisher_TensorFlow.keras") -> None:
        """Load a model and tokenizer from disk or create new ones if they don't exist."""
        if os.path.exists(model_path):
            self.model = load_model(model_path)
            logging.info(
                f"Model loaded from '{model_path}'"
            )
        else:
            self.model = self._create_model()
            self.model.save(model_path)
            logging.info(
                f"New model created and saved to '{model_path}'"
            )
        tokenizer_path = f"{config.TRAINING_DATA_PATH}/tokenizer.pkl"
        if os.path.exists(tokenizer_path):
            with open(tokenizer_path, "rb") as f:
                self.tokenizer = pickle.load(f)
            self.vocab_size = len(self.tokenizer.word_index) + 1
            logging.info(
                f"Tokenizer loaded from '{tokenizer_path}', total tokens: {len(self.tokenizer.word_index)}"
            )
        else:
            self.tokenizer = Tokenizer(num_words=self.max_vocab_size, oov_token="<OOV>")
            with open(tokenizer_path, "wb") as f:
                pickle.dump(self.tokenizer, f)
            logging.info(
                f"New tokenizer created and saved to '{tokenizer_path}', total tokens: {len(self.tokenizer.word_index)}"
            )

    def _create_model(self) -> Sequential:
        """Define and return a new TensorFlow model."""
        model = Sequential(
            [
                Input(shape=(self.max_sequence_length,)),
                Embedding(self.max_vocab_size, 128),
                LSTM(64, return_sequences=False),
                Dropout(0.3),
                Dense(1, activation='sigmoid'),
            ]
        )
        model.compile(optimizer=Adam(), loss='binary_crossentropy', metrics=['accuracy'])
        return model

    def unload_model(self) -> None:
        """Unload the model and clear resources."""
        if self.model:
            self.model = None
            from keras import backend as K
            )

            K.clear_session()
            import gc

            gc.collect()
            logging.info("Model unloaded.")
        else:
            logging.debug("No model is loaded to unload.")
