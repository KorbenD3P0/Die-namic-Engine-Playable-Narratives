# main.py
import os
import sys
import logging
from kivy.utils import platform

# This is the most critical step. It tells Python that the 'fd_terminal' folder
# is a place where it can find modules to import.
# We add the current directory (where 'main.py' and 'fd_terminal' live) to the path.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def setup_initial_logging():
    """Sets up a basic logger before the Kivy app takes over."""
    handlers = []
    # Always log to logcat/console
    handlers.append(logging.StreamHandler())
    # On Android, also log to a file
    if platform == "android":
        try:
            handlers.append(logging.FileHandler("/sdcard/fdt_log.txt"))
        except Exception as e:
            print(f"Could not create file handler for logging: {e}")

    logging.basicConfig(
        level=logging.INFO,
        format='FDTAPP %(asctime)s - %(levelname)s - %(name)s - %(message)s',
        handlers=handlers
    )
    print("FDTAPP: About to initialize logger")
    logging.info("Launcher: Initializing...")
    print("FDTAPP: Logger initialized")

def request_android_permissions():
    if platform == "android":
        try:
            from android.permissions import request_permissions, Permission  # type: ignore
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
        except ImportError:
            logging.warning("Android permissions module not available")

def main():
    """The main entry point for the application."""
    setup_initial_logging()
    
    try:
        # Now that the path is set, we can perform a non-relative import.
        # We are telling Python to "from the fd_terminal package, import the main scroll."
        from fd_terminal.main import FinalDestinationApp
        
        logging.info("Launcher: Starting the FinalDestinationApp.")
        FinalDestinationApp().run()
        
    except ImportError as e:
        logging.critical(f"FATAL LAUNCH ERROR: Could not import the application. Check that 'fd_terminal' is a valid package.", exc_info=True)
        # In a real application, you might show a GUI error here.
        input(f"Fatal Error: {e}\nPress Enter to exit.")
    except Exception as e:
        logging.critical(f"An unexpected fatal error occurred during launch.", exc_info=True)
        input(f"An unexpected fatal error occurred: {e}\nPress Enter to exit.")

# This is the command to start everything when you run this file.
if __name__ == "__main__":
    main()