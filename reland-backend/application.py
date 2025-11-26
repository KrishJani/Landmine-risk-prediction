"""
Elastic Beanstalk entry point.
EB expects 'application' variable to be the WSGI app.
"""
import importlib.util
import os

# Import backend-app.py (file has hyphen, so we need to use importlib)
backend_app_path = os.path.join(os.path.dirname(__file__), 'backend-app.py')
spec = importlib.util.spec_from_file_location("backend_app", backend_app_path)
backend_app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_app_module)

# Get the app from the module
app = backend_app_module.app

# Elastic Beanstalk expects this variable name
application = app

if __name__ == "__main__":
    application.run()

