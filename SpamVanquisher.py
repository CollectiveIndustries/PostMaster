import logging

from PostOffice import PostOffice

def main():
    # Initialize PostOffice
    post_office = PostOffice()

    # Start the threads
    training_thread = post_office.start_trainer()
    processing_thread = post_office.start_postman()

    logging.info("Daemon threads for training and processing started.")

    # Keep the main thread alive
    try:
        while True:
            pass
    except KeyboardInterrupt:
        logging.info("Stopping threads...")
        post_office.stop_threads()
        training_thread.join()
        processing_thread.join()
        logging.info("Threads stopped.")

if __name__ == "__main__":
    main()
