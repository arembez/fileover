"""
app/controllers_collection.py

Controller discovery and management system for FileOver microservice.
Dynamically discovers and loads controller classes from the filesystem,
and provides instantiation based on session requests.

Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
MIT License (see LICENSE or https://opensource.org/licenses/MIT)
"""

import importlib.util
import inspect
from pathlib import Path
from typing import Dict, Type, Optional
from pydantic import ValidationError

from app.base import EndpointController
from app.types import SessionInitRequest


class ControllersCollection:
    """
    Manages discovery and instantiation of endpoint controllers.
    
    This class automatically discovers all controller classes in the
    application directory that inherit from EndpointController, and
    provides a dictionary-like interface to access them by name.
    
    Attributes:
        app_path (Path): Path to the application directory
        controllers (Dict[str, Type[EndpointController]]): Dictionary mapping
            controller class names to their types
    """
    
    def __init__(self):
        """
        Initialize the controllers collection and discover available controllers.
        """
        self.app_path = Path(__file__).parent
        self.controllers: Dict[str, Type[EndpointController]] = {}
        self.discover()
        
    def discover(self) -> Dict[str, Type[EndpointController]]:
        """
        Discover all controller classes in the application directory.
        
        Recursively scans all subdirectories (except __pycache__ and __init__.py)
        for Python files containing classes that inherit from EndpointController.
        
        Returns:
            Dict[str, Type[EndpointController]]: Updated controllers dictionary
        """
        for subdir in self.app_path.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name.startswith('__'):
                continue
                
            for py_file in subdir.rglob("*.py"):
                if py_file.name == "__init__.py":
                    continue
                self._load_controller_from_file(py_file)
        
        return self.controllers
    
    def _load_controller_from_file(self, file_path: Path):
        """
        Load a controller class from a Python file.
        
        Args:
            file_path (Path): Path to the Python file to load
        """
        rel_path = file_path.relative_to(self.app_path.parent)
        module_name = str(rel_path.with_suffix('')).replace('/', '.')
        
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, EndpointController) and 
                    obj != EndpointController):
                    self.controllers[name] = obj
                        
        except Exception as e:
            print(f"Failed to load {file_path}: {e}")

    def _validate_params(self, controller_class, params: dict) -> dict:
        """
        Validate parameters using controller's declared validators.
        Returns validated params (after possible Pydantic transformation).
        Raises ValueError with detailed message on failure.
        """
        model_cls = controller_class.get_parameter_model()
        if model_cls is not None:
            try:
                model = model_cls(**params)
                return model.model_dump()  # или .dict()
            except ValidationError as e:
                errors = []
                for err in e.errors():
                    field = ".".join(str(loc) for loc in err["loc"])
                    errors.append(f"{field}: {err['msg']}")
                raise ValueError(f"Validation error: {'; '.join(errors)}")

        required = controller_class.get_required_params()
        if required:
            missing = [f for f in required if f not in params]
            if missing:
                raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        return params
    
    def _init_controller(self, controller_class, params: dict) -> EndpointController:
        """
        Instantiate the controller class with validated parameters.
        Handles TypeError and any other instantiation errors.
        """
        try:
            return controller_class(**params)
        except TypeError as e:
            raise ValueError(f"Invalid parameters for controller {controller_class.__name__}: {e}")
        except Exception as e:
            raise ValueError(f"Failed to initialize controller {controller_class.__name__}: {e}")
        
    def __getitem__(self, key) -> Optional[EndpointController]:
        """
        Get a controller instance by SessionInitRequest or controller name.
        """
        if isinstance(key, SessionInitRequest):
            controller_class = self.controllers.get(key.controller)
            if not controller_class:
                raise ValueError(
                    f"Unknown controller: '{key.controller}'. "
                    f"Available: {', '.join(self.controllers.keys())}"
                )

            params = key.model_dump()
            if key.model_extra:
                params.update(key.model_extra)
            params.pop('controller', None)

            validated_params = self._validate_params(controller_class, params)

            return self._init_controller(controller_class, validated_params)

        elif isinstance(key, str):
            return self.controllers.get(key)

        else:
            raise TypeError(f"Expected SessionInitRequest or str, got {type(key)}")
    
    def __call__(self, controller: str) -> Optional[Type[EndpointController]]:
        """
        Get a controller class by name (callable interface).
        
        Args:
            controller (str): Name of the controller class
            
        Returns:
            Optional[Type[EndpointController]]: Controller class or None if not found
        """
        return self.controllers.get(controller)


# Singleton instance for global use
controllers = ControllersCollection()