from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel, ValidationError

# Clase de configuración utilizando Pydantic para validación


class ConfigurationModel(BaseModel):
    world: str
    launch_file: str
    name: str
    exercise_id: str

# Definición de la clase de datos


@dataclass
class ConfigurationManager:
    configuration: ConfigurationModel

    @staticmethod
    def validate(configuration: dict):
        try:
            return ConfigurationModel(**configuration)
        except ValidationError as e:
            raise ValueError(f"Invalid configuration: {e}")
