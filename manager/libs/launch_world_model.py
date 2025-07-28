"""Module for managing and validating robotics application launch world configs."""

from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel, ValidationError

# Clase de configuración utilizando Pydantic para validación


class ConfigurationModel(BaseModel):
    """Pydantic model for robotics application world type and launch file config."""

    type: str
    launch_file_path: str


# Definición de la clase de datos


@dataclass
class ConfigurationManager:
    """Manager for robotics application configuration validation and storage."""

    configuration: ConfigurationModel

    @staticmethod
    def validate(configuration: dict):
        """Validate the given configuration dictionary using the ConfigurationModel.

        Args:
            configuration (dict): The configuration data to validate.

        Returns:
            ConfigurationModel: The validated configuration model.

        Raises:
            ValueError: If the configuration is invalid.
        """
        try:
            return ConfigurationModel(**configuration)
        except ValidationError as e:
            raise ValueError(f"Invalid configuration: {e}")
