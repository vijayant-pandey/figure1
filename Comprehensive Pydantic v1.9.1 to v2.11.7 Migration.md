<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" class="logo" width="120"/>

# Comprehensive Pydantic v1.9.1 to v2.11.7 Migration Guide

## Overview

This migration guide provides extremely detailed instructions for upgrading from pydantic.v1v1.9.1 (with extras) to v2.11.7. This is a major version upgrade with significant breaking changes that require careful attention to syntax modifications, configuration updates, and behavioral changes.

## Table of Contents

1. [Installation and Environment Setup](#installation-and-environment-setup)
2. [BaseModel Core Changes](#basemodel-core-changes)
3. [Field Configuration Updates](#field-configuration-updates)
4. [Configuration System Overhaul](#configuration-system-overhaul)
5. [Validation System Transformation](#validation-system-transformation)
6. [Serialization System Changes](#serialization-system-changes)
7. [Type System Updates](#type-system-updates)
8. [Dataclasses Modifications](#dataclasses-modifications)
9. [JSON Schema Generation Changes](#json-schema-generation-changes)
10. [Moved and Deprecated Features](#moved-and-deprecated-features)

## Installation and Environment Setup

### Installing Pydantic v2.11.7

**Update your requirements.txt:**

```diff
- pydantic==1.9.1
+ pydantic==2.11.7
```

**Install the new version:**

```bash
pip install -U pydantic==2.11.7
```


### Migration Tool Usage

Pydantic provides an automated migration tool to help with the transition:

```bash
pip install bump-pydantic
cd /path/to/your/project
bump-pydantic your_package_name
```

**Important:** This tool is in beta and may not catch all changes. Always review the automated changes manually[1].

### Gradual Migration Strategy

For large codebases, you can maintain both versions during migration:

```python
# Option 1: Use v1 features in v2 environment
from pydantic.v1 import BaseModel as V1BaseModel
from pydantic.v1 import BaseModel as V2BaseModel

# Option 2: Conditional imports
try:
    from pydantic.v1 import BaseModel
except ImportError:
    from pydantic.v1 import BaseModel
```


## BaseModel Core Changes

### Method Renaming

All non-deprecated BaseModel methods now follow the `model_.*` naming convention:

```python
# v1.9.1 syntax
class UserV1(BaseModel):
    name: str
    age: int

user_dict = user.dict()                    # ❌ Deprecated
user_json = user.json()                    # ❌ Deprecated
parsed_user = User.parse_obj(data)         # ❌ Deprecated
schema = User.schema()                     # ❌ Deprecated
copied_user = user.copy()                  # ❌ Deprecated

# v2.11.7 syntax
class UserV2(BaseModel):
    name: str
    age: int

user_dict = user.model_dump()              # ✅ New method
user_json = user.model_dump_json()         # ✅ New method
parsed_user = User.model_validate(data)    # ✅ New method
schema = User.model_json_schema()          # ✅ New method
copied_user = user.model_copy()            # ✅ New method
```


### Complete Method Mapping Table

| Pydantic v1.9.1 | Pydantic v2.11.7 | Status |
| :-- | :-- | :-- |
| `dict()` | `model_dump()` | Deprecated but available |
| `json()` | `model_dump_json()` | Deprecated but available |
| `parse_obj()` | `model_validate()` | Deprecated but available |
| `parse_raw()` | `model_validate_json()` | Deprecated, limited functionality |
| `parse_file()` | Load file then `model_validate()` | Removed |
| `schema()` | `model_json_schema()` | Deprecated but available |
| `copy()` | `model_copy()` | Deprecated but available |
| `construct()` | `model_construct()` | Deprecated but available |
| `from_orm()` | `model_validate()` + config | Deprecated but available |
| `update_forward_refs()` | `model_rebuild()` | Deprecated but available |

### Data Loading Changes

**v1.9.1 approach:**

```python
# Multiple parsing methods
user = User.parse_obj({"name": "John", "age": 30})
user = User.parse_raw('{"name": "John", "age": 30}')
user = User.parse_file('user.json')
```

**v2.11.7 approach:**

```python
# Unified validation approach
user = User.model_validate({"name": "John", "age": 30})
user = User.model_validate_json('{"name": "John", "age": 30}')

# For file loading, load first then validate
import json
with open('user.json') as f:
    data = json.load(f)
user = User.model_validate(data)
```


### ORM Integration Changes

**v1.9.1 syntax:**

```python
class User(BaseModel):
    name: str
    age: int
    
    class Config:
        orm_mode = True

# Usage
user = User.from_orm(orm_instance)
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import BaseModel, ConfigDict

class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    name: str
    age: int

# Usage
user = User.model_validate(orm_instance)
```


### Constructor and Equality Changes

**Important behavioral changes:**

1. **Mutable objects are now copied during validation:**
```python
# v2.11.7 behavior
data = {"items": [1, 2, 3]}
user = User(data=data)
data["items"].append(4)  # Won't affect user.data
```

2. **Model equality is stricter:**
```python
# v1.9.1: Models could equal dicts
user_dict = {"name": "John", "age": 30}
user = User(**user_dict)
assert user == user_dict  # ❌ This worked in v1

# v2.11.7: Models only equal other models
user1 = User(name="John", age=30)
user2 = User(name="John", age=30)
assert user1 == user2  # ✅ This works
assert user1 == {"name": "John", "age": 30}  # ❌ This fails
```


### Custom Root Models

**v1.9.1 syntax:**

```python
class RootModel(BaseModel):
    __root__: List[str]
    
    def __iter__(self):
        return iter(self.__root__)
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import RootModel
from typing import List

class MyRootModel(RootModel[List[str]]):
    def __iter__(self):
        return iter(self.root)
```


## Field Configuration Updates

### Field Parameter Changes

**Removed parameters:**

- `const` → Use `Literal` type instead
- `min_items`/`max_items` → Use `min_length`/`max_length`
- `unique_items` → Removed (use `Set` type instead)
- `allow_mutation` → Use `frozen=True` instead
- `regex` → Use `pattern` instead
- `final` → Use `typing.Final` instead

**v1.9.1 syntax:**

```python
from pydantic.v1 import BaseModel, Field
from typing import List

class Product(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    tags: List[str] = Field(min_items=1, max_items=10, unique_items=True)  # ❌
    price: float = Field(gt=0, const=True)  # ❌
    description: str = Field(regex=r'^[A-Za-z\s]+$')  # ❌
    immutable_field: str = Field(allow_mutation=False)  # ❌
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import BaseModel, Field
from typing import List, Set, Literal, Final
from typing_extensions import Annotated

class Product(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    tags: Set[str] = Field(min_length=1, max_length=10)  # ✅ Use Set for uniqueness
    price: Literal[9.99] = Field(gt=0)  # ✅ Use Literal for const
    description: str = Field(pattern=r'^[A-Za-z\s]+$')  # ✅ Use pattern
    immutable_field: str = Field(frozen=True)  # ✅ Use frozen
    
    # Alternative using Final
    final_field: Final[str] = "unchangeable"
```


### Alias Behavior Changes

**v1.9.1 behavior:**

```python
class User(BaseModel):
    name: str = Field(alias="user_name")
    
# Field.alias returned field name when no alias was set
field_info = User.__fields__['name']
print(field_info.alias)  # Returns "user_name" or "name" if no alias
```

**v2.11.7 behavior:**

```python
class User(BaseModel):
    name: str = Field(alias="user_name")
    
# Field.alias returns None when no alias is set
field_info = User.model_fields['name']
print(field_info.alias)  # Returns "user_name" or None if no alias
```


### JSON Schema Extra Configuration

**v1.9.1 syntax:**

```python
class User(BaseModel):
    name: str = Field(title="User Name", custom_property="value")  # ❌
```

**v2.11.7 syntax:**

```python
class User(BaseModel):
    name: str = Field(
        title="User Name",
        json_schema_extra={"custom_property": "value"}  # ✅
    )
```


### Generic Type Constraints

**v1.9.1 syntax:**

```python
class Container(BaseModel):
    items: List[str] = Field(min_length=3)  # Applied to list
```

**v2.11.7 syntax:**

```python
from typing_extensions import Annotated

class Container(BaseModel):
    # Constraints now apply to individual items
    items: List[Annotated[str, Field(min_length=3)]]  # ✅ Applied to each string
    
    # Or apply to the list itself
    items_list: List[str] = Field(min_length=3)  # ✅ Applied to list length
```


## Configuration System Overhaul

### Config Class to model_config Dictionary

**v1.9.1 syntax:**

```python
class User(BaseModel):
    name: str
    age: int
    
    class Config:
        use_enum_values = True
        validate_assignment = True
        orm_mode = True
        allow_population_by_field_name = True
        anystr_lower = True
        anystr_strip_whitespace = True
        schema_extra = {"example": {"name": "John", "age": 30}}
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import BaseModel, ConfigDict

class User(BaseModel):
    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
        from_attributes=True,  # ✅ orm_mode renamed
        populate_by_name=True,  # ✅ allow_population_by_field_name renamed
        str_to_lower=True,  # ✅ anystr_lower renamed
        str_strip_whitespace=True,  # ✅ anystr_strip_whitespace renamed
        json_schema_extra={"example": {"name": "John", "age": 30}}  # ✅ schema_extra renamed
    )
    
    name: str
    age: int
```


### Comprehensive Configuration Mapping

**Removed configurations:**

- `allow_mutation` → Use `frozen=True` in model_config
- `error_msg_templates` → No direct replacement
- `fields` → Use `Annotated` for field modifications
- `getter_dict` → Removed with orm_mode changes
- `smart_union` → Default behavior in v2
- `underscore_attrs_are_private` → Always True in v2
- `json_loads`/`json_dumps` → Use serializers instead
- `copy_on_model_validation` → Removed
- `post_init_call` → Removed

**Renamed configurations:**


| v1.9.1 | v2.11.7 |
| :-- | :-- |
| `allow_population_by_field_name` | `populate_by_name` |
| `anystr_lower` | `str_to_lower` |
| `anystr_strip_whitespace` | `str_strip_whitespace` |
| `anystr_upper` | `str_to_upper` |
| `keep_untouched` | `ignored_types` |
| `max_anystr_length` | `str_max_length` |
| `min_anystr_length` | `str_min_length` |
| `orm_mode` | `from_attributes` |
| `schema_extra` | `json_schema_extra` |
| `validate_all` | `validate_default` |

### Configuration Inheritance

**v2.11.7 configuration inheritance:**

```python
class BaseUser(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )

class ExtendedUser(BaseUser):
    model_config = ConfigDict(
        # Inherits from BaseUser and adds/overrides
        frozen=True,
        str_to_lower=True
    )
```


## Validation System Transformation

### Validator Decorator Changes

**v1.9.1 syntax:**

```python
from pydantic.v1 import BaseModel, validator, root_validator

class User(BaseModel):
    name: str
    age: int
    email: str
    
    @validator('name')
    def validate_name(cls, v):
        if len(v) < 2:
            raise ValueError('Name must be at least 2 characters')
        return v.title()
    
    @validator('age')
    def validate_age(cls, v):
        if v < 0:
            raise ValueError('Age must be positive')
        return v
    
    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email')
        return v
    
    @root_validator
    def validate_user(cls, values):
        if values.get('age', 0) < 13 and '@' not in values.get('email', ''):
            raise ValueError('Children must have guardian email')
        return values
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import BaseModel, field_validator, model_validator

class User(BaseModel):
    name: str
    age: int
    email: str
    
    @field_validator('name')
    def validate_name(cls, v):
        if len(v) < 2:
            raise ValueError('Name must be at least 2 characters')
        return v.title()
    
    @field_validator('age')
    def validate_age(cls, v):
        if v < 0:
            raise ValueError('Age must be positive')
        return v
    
    @field_validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email')
        return v
    
    @model_validator(mode='after')
    def validate_user(cls, values):
        if values.age < 13 and '@' not in values.email:
            raise ValueError('Children must have guardian email')
        return values
```


### ValidationInfo Usage

**v1.9.1 syntax:**

```python
@validator('confirm_password')
def passwords_match(cls, v, values, **kwargs):
    if 'password' in values and v != values['password']:
        raise ValueError('Passwords do not match')
    return v
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import field_validator, ValidationInfo

@field_validator('confirm_password')
def passwords_match(cls, v, info: ValidationInfo):
    if 'password' in info.data and v != info.data['password']:
        raise ValueError('Passwords do not match')
    return v
```


### Model Validator Modes

**v2.11.7 introduces different validator modes:**

```python
from pydantic.v1 import BaseModel, model_validator

class User(BaseModel):
    name: str
    age: int
    
    @model_validator(mode='before')
    def validate_before_parsing(cls, values):
        """Runs before field validation"""
        if isinstance(values, dict):
            values['name'] = values.get('name', '').strip()
        return values
    
    @model_validator(mode='after')
    def validate_after_parsing(cls, values):
        """Runs after field validation"""
        if values.age < 0:
            raise ValueError('Age cannot be negative')
        return values
    
    @model_validator(mode='wrap')
    def validate_wrap(cls, values, handler):
        """Wraps the entire validation process"""
        # Before validation
        result = handler(values)
        # After validation
        return result
```


### Type Coercion Changes

**v1.9.1 behavior (automatic coercion):**

```python
class User(BaseModel):
    age: int
    height: str

# These worked in v1.9.1
user1 = User(age=25.0, height=180)        # ✅ float → int, int → str
user2 = User(age="25", height=180)        # ✅ str → int, int → str
```

**v2.11.7 behavior (stricter coercion):**

```python
class User(BaseModel):
    age: int
    height: str

# These work in v2.11.7
user1 = User(age=25.0, height="180")      # ✅ float → int (if .0), explicit str
user2 = User(age="25", height="180")      # ✅ str → int, explicit str

# These fail in v2.11.7
try:
    user3 = User(age=25.5, height=180)    # ❌ float with decimal → int fails
except ValidationError:
    pass

# Enable specific coercion
class UserWithCoercion(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    
    age: int
    height: str

user4 = UserWithCoercion(age="25", height=180)  # ✅ Now works
```


### Always Parameter Replacement

**v1.9.1 syntax:**

```python
@validator('field', always=True)
def validate_field(cls, v):
    return v or "default"
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import Field, field_validator

class Model(BaseModel):
    field: str = Field(validate_default=True)
    
    @field_validator('field')
    def validate_field(cls, v):
        return v or "default"
```


## Serialization System Changes

### New Serialization Decorators

**v2.11.7 introduces powerful serialization decorators:**

```python
from pydantic.v1 import BaseModel, field_serializer, model_serializer, computed_field
from datetime import datetime
from typing import Any, Dict

class User(BaseModel):
    name: str
    birth_date: datetime
    _internal_id: int = 12345
    
    @field_serializer('birth_date')
    def serialize_birth_date(self, value: datetime) -> str:
        return value.strftime('%Y-%m-%d')
    
    @computed_field
    @property
    def age(self) -> int:
        today = datetime.now()
        return today.year - self.birth_date.year
    
    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        # Custom serialization for entire model
        return {
            'user_name': self.name,
            'birth_year': self.birth_date.year,
            'computed_age': self.age
        }
```


### JSON Encoders Deprecation

**v1.9.1 syntax:**

```python
from datetime import datetime
from decimal import Decimal

class User(BaseModel):
    name: str
    created_at: datetime
    balance: Decimal
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v)
        }
```

**v2.11.7 syntax (preferred):**

```python
from pydantic.v1 import BaseModel, field_serializer
from datetime import datetime
from decimal import Decimal

class User(BaseModel):
    name: str
    created_at: datetime
    balance: Decimal
    
    @field_serializer('created_at')
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()
    
    @field_serializer('balance')
    def serialize_decimal(self, value: Decimal) -> str:
        return str(value)
```

**v2.11.7 syntax (legacy support with deprecation warning):**

```python
from pydantic.v1 import BaseModel, ConfigDict
from datetime import datetime
from decimal import Decimal

class User(BaseModel):
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v)
        }
    )
    
    name: str
    created_at: datetime
    balance: Decimal
```


### Computed Fields

**v2.11.7 computed fields:**

```python
from pydantic.v1 import BaseModel, computed_field

class Rectangle(BaseModel):
    width: float
    height: float
    
    @computed_field
    @property
    def area(self) -> float:
        return self.width * self.height
    
    @computed_field
    @property
    def perimeter(self) -> float:
        return 2 * (self.width + self.height)

# Usage
rect = Rectangle(width=10, height=5)
print(rect.area)        # 50.0
print(rect.perimeter)   # 30.0
print(rect.model_dump()) # Includes computed fields
```


## Type System Updates

### Union Type Handling

**v1.9.1 behavior:**

```python
from typing import Union

class Model(BaseModel):
    value: Union[int, str]

# v1.9.1: Always tried to convert to first matching type
model = Model(value='123')  # Resulted in value=123 (int)
```

**v2.11.7 behavior:**

```python
from typing import Union

class Model(BaseModel):
    value: Union[int, str]

# v2.11.7: Preserves input type when possible
model = Model(value='123')  # Results in value='123' (str)

# To get v1.9.1 behavior:
class ModelV1Behavior(BaseModel):
    value: Union[int, str] = Field(union_mode='left_to_right')
```


### Optional Field Behavior

**v1.9.1 behavior:**

```python
from typing import Optional

class User(BaseModel):
    name: str
    email: Optional[str]  # Not required, defaults to None
```

**v2.11.7 behavior:**

```python
from typing import Optional

class User(BaseModel):
    name: str                           # Required, cannot be None
    email: Optional[str]                # Required, can be None
    bio: Optional[str] = None          # Not required, can be None, defaults to None
    age: Optional[int] = Field(default=None)  # Not required, can be None
```


### Generic Model Changes

**v1.9.1 syntax:**

```python
from pydantic.generics import GenericModel
from typing import TypeVar, Generic

T = TypeVar('T')

class GenericContainer(GenericModel, Generic[T]):
    item: T
    count: int
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import BaseModel
from typing import TypeVar, Generic

T = TypeVar('T')

class GenericContainer(BaseModel, Generic[T]):
    item: T
    count: int

# Usage
string_container = GenericContainer[str](item="hello", count=1)
int_container = GenericContainer[int](item=42, count=1)
```


### Custom Type Definition

**v1.9.1 syntax:**

```python
class CustomType:
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v):
        # Custom validation logic
        return v
    
    @classmethod
    def __modify_schema__(cls, field_schema):
        # Custom schema modification
        field_schema.update({'custom_property': 'value'})
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import GetCoreSchemaHandler
from pydantic_core import core_schema
from typing import Any

class CustomType:
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        # Return core schema for validation
        return core_schema.str_schema()
    
    @classmethod
    def __get_pydantic_json_schema__(cls, schema: core_schema.CoreSchema, handler) -> dict:
        # Return JSON schema
        return {'type': 'string', 'custom_property': 'value'}
```


## Dataclasses Modifications

### Validation Input Changes

**v1.9.1 behavior:**

```python
from pydantic.dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int

# v1.9.1: Accepted tuples
user = User(("John", 30))  # ✅ Worked
```

**v2.11.7 behavior:**

```python
from pydantic.dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int

# v2.11.7: Only accepts dicts or keyword arguments
user = User(name="John", age=30)        # ✅ Works
user = User({"name": "John", "age": 30})  # ❌ Won't work
```


### Post-Init Changes

**v1.9.1 behavior:**

```python
from pydantic.dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int
    
    def __post_init__(self):
        # Ran before validation
        self.name = self.name.strip()
    
    def __post_init_post_parse__(self):
        # Ran after validation
        self.name = self.name.title()
```

**v2.11.7 behavior:**

```python
from pydantic.dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int
    
    def __post_init__(self):
        # Now runs after validation
        self.name = self.name.title()
    
    # __post_init_post_parse__ is removed
```


### Extra Fields Handling

**v1.9.1 behavior:**

```python
from pydantic.dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int
    
    class Config:
        extra = 'allow'

# Extra fields were stored as attributes
user = User(name="John", age=30, extra_field="value")
print(user.extra_field)  # "value"
```

**v2.11.7 behavior:**

```python
from pydantic.dataclasses import dataclass
from pydantic.v1 import ConfigDict

@dataclass(config=ConfigDict(extra='ignore'))
class User:
    name: str
    age: int

# Extra fields are ignored, not stored
user = User(name="John", age=30, extra_field="value")
# user.extra_field doesn't exist
```


### TypeAdapter for Dataclasses

**v1.9.1 usage:**

```python
from pydantic.dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int

# Direct access to underlying model
schema = User.__pydantic_model__.schema()
```

**v2.11.7 usage:**

```python
from pydantic.dataclasses import dataclass
from pydantic.v1 import TypeAdapter

@dataclass
class User:
    name: str
    age: int

# Use TypeAdapter for validation and schema generation
adapter = TypeAdapter(User)
schema = adapter.json_schema()
validated = adapter.validate_python({"name": "John", "age": 30})
```


## JSON Schema Generation Changes

### Schema Generation Updates

**v1.9.1 behavior:**

```python
class User(BaseModel):
    name: str
    age: Optional[int] = None

schema = User.schema()
# Optional fields didn't indicate null was allowed
```

**v2.11.7 behavior:**

```python
class User(BaseModel):
    name: str
    age: Optional[int] = None

schema = User.model_json_schema()
# Optional fields now properly indicate null is allowed
```


### Custom Schema Generation

**v1.9.1 syntax:**

```python
class User(BaseModel):
    name: str
    age: int
    
    class Config:
        schema_extra = {
            "example": {"name": "John", "age": 30}
        }
        
        # Or as a function
        @staticmethod
        def schema_extra(schema, model_class):
            schema['custom_property'] = 'value'
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import BaseModel, ConfigDict

class User(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"name": "John", "age": 30}
        }
    )
    
    name: str
    age: int

# Or as a function
def schema_extra(schema, model_class):
    schema['custom_property'] = 'value'

class UserWithFunction(BaseModel):
    model_config = ConfigDict(json_schema_extra=schema_extra)
    
    name: str
    age: int
```


### GenerateJsonSchema Customization

**v2.11.7 advanced schema customization:**

```python
from pydantic.v1 import BaseModel
from pydantic.json_schema import GenerateJsonSchema
from typing import Any

class CustomJsonSchema(GenerateJsonSchema):
    def generate_schema(self, schema: Any) -> dict:
        json_schema = super().generate_schema(schema)
        # Custom modifications
        json_schema['custom_property'] = 'value'
        return json_schema

class User(BaseModel):
    name: str
    age: int

# Use custom schema generator
schema = User.model_json_schema(schema_generator=CustomJsonSchema)
```


## Moved and Deprecated Features

### BaseSettings Migration

**v1.9.1 usage:**

```python
from pydantic.v1 import BaseSettings

class Settings(BaseSettings):
    database_url: str
    debug: bool = False
    
    class Config:
        env_prefix = 'APP_'
```

**v2.11.7 usage:**

```python
# Install pydantic-settings separately
# pip install pydantic-settings

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='APP_')
    
    database_url: str
    debug: bool = False
```


### URL and Network Types

**v1.9.1 behavior:**

```python
from pydantic.v1 import BaseModel, AnyUrl

class Website(BaseModel):
    url: AnyUrl

site = Website(url="https://example.com")
print(site.url)  # AnyUrl inherited from str
print(site.url.startswith("https"))  # ✅ Worked directly
```

**v2.11.7 behavior:**

```python
from pydantic.v1 import BaseModel, AnyUrl

class Website(BaseModel):
    url: AnyUrl

site = Website(url="https://example.com")
print(str(site.url))  # Must convert to str
print(str(site.url).startswith("https"))  # ✅ Works with conversion
```


### Constrained Types

**v1.9.1 syntax:**

```python
from pydantic.v1 import BaseModel, ConstrainedStr, ConstrainedInt

class MyConstrainedStr(ConstrainedStr):
    min_length = 3
    max_length = 50

class MyConstrainedInt(ConstrainedInt):
    ge = 0
    le = 100

class User(BaseModel):
    name: MyConstrainedStr
    age: MyConstrainedInt
```

**v2.11.7 syntax:**

```python
from pydantic.v1 import BaseModel, Field
from typing_extensions import Annotated

MyConstrainedStr = Annotated[str, Field(min_length=3, max_length=50)]
MyConstrainedInt = Annotated[int, Field(ge=0, le=100)]

class User(BaseModel):
    name: MyConstrainedStr
    age: MyConstrainedInt
```


### Deprecated Function Replacements

**v1.9.1 functions:**

```python
from pydantic.tools import parse_obj_as, schema_of
from pydantic.v1 import validate_arguments

# Parse arbitrary objects
parsed = parse_obj_as(List[int], ["1", "2", "3"])

# Get schema for types
schema = schema_of(List[int])

# Validate function arguments
@validate_arguments
def my_function(x: int, y: str) -> str:
    return f"{x}: {y}"
```

**v2.11.7 replacements:**

```python
from pydantic.v1 import TypeAdapter, validate_call
from typing import List

# Use TypeAdapter instead
adapter = TypeAdapter(List[int])
parsed = adapter.validate_python(["1", "2", "3"])
schema = adapter.json_schema()

# Use validate_call instead
@validate_call
def my_function(x: int, y: str) -> str:
    return f"{x}: {y}"
```


## Complete Migration Checklist

### Pre-Migration Steps

1. **Backup your codebase**
2. **Install bump-pydantic tool**: `pip install bump-pydantic`
3. **Run automated migration**: `bump-pydantic your_package`
4. **Review all changes manually**

### Core Changes to Address

- [ ] Update all `dict()` calls to `model_dump()`
- [ ] Update all `json()` calls to `model_dump_json()`
- [ ] Update all `parse_obj()` calls to `model_validate()`
- [ ] Update all `parse_raw()` calls to `model_validate_json()`
- [ ] Replace `parse_file()` with manual file loading + `model_validate()`
- [ ] Update all `schema()` calls to `model_json_schema()`
- [ ] Update all `copy()` calls to `model_copy()`
- [ ] Update all `from_orm()` calls to `model_validate()` with `from_attributes=True`


### Configuration Updates

- [ ] Convert `Config` classes to `model_config` dictionaries
- [ ] Update configuration parameter names (see mapping table)
- [ ] Remove unsupported configuration options
- [ ] Update `schema_extra` to `json_schema_extra`


### Validation Changes

- [ ] Replace `@validator` with `@field_validator`
- [ ] Replace `@root_validator` with `@model_validator`
- [ ] Update validator function signatures
- [ ] Replace `always=True` with `validate_default=True` in Field
- [ ] Update field validation for cross-field validation using `ValidationInfo`


### Field Updates

- [ ] Replace `const` with `Literal` types
- [ ] Update `min_items`/`max_items` to `min_length`/`max_length`
- [ ] Remove `unique_items` and use `Set` types instead
- [ ] Replace `allow_mutation` with `frozen`
- [ ] Update `regex` to `pattern`
- [ ] Update constraint applications for generic types


### Type System Updates

- [ ] Update `Optional` field behavior (now required by default)
- [ ] Replace `GenericModel` with `BaseModel` + `Generic`
- [ ] Update union type handling if needed
- [ ] Update custom type definitions


### External Dependencies

- [ ] Install `pydantic-settings` if using `BaseSettings`
- [ ] Install `pydantic-extra-types` if using `Color` or `PaymentCard` types
- [ ] Update imports for moved modules


### Testing

- [ ] Run comprehensive tests
- [ ] Test serialization/deserialization
- [ ] Test validation behavior
- [ ] Test configuration inheritance
- [ ] Test custom validators
- [ ] Test JSON schema generation


### Performance Considerations

- [ ] Review type coercion changes
- [ ] Update regex patterns if using complex patterns
- [ ] Consider using `TypeAdapter` for non-model types
- [ ] Review serialization performance


## Common Pitfalls and Solutions

### 1. Silent Failures Due to Method Renaming

**Problem**: Old method names still work but are deprecated
**Solution**: Use search and replace systematically

```bash
# Find all usages
grep -r "\.dict()" your_project/
grep -r "\.json()" your_project/
grep -r "\.parse_obj(" your_project/
```


### 2. Configuration Not Taking Effect

**Problem**: Using old `Config` class syntax
**Solution**: Always use `model_config` dictionary

```python
# Wrong
class MyModel(BaseModel):
    class Config:
        extra = 'allow'

# Correct
class MyModel(BaseModel):
    model_config = ConfigDict(extra='allow')
```


### 3. Validation Errors on Previously Working Code

**Problem**: Stricter type coercion in v2
**Solution**: Enable specific coercion or update types

```python
# Enable number to string coercion
class MyModel(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
```


### 4. Union Type Behavior Changes

**Problem**: Union types now preserve input types
**Solution**: Use `union_mode='left_to_right'` for old behavior

```python
class MyModel(BaseModel):
    value: Union[int, str] = Field(union_mode='left_to_right')
```


### 5. Optional Field Confusion

**Problem**: `Optional[T]` is now required if no default is provided
**Solution**: Explicitly provide defaults

```python
# v1.9.1 behavior
class User(BaseModel):
    name: Optional[str]  # Not required, defaulted to None

# v2.11.7 equivalent
class User(BaseModel):
    name: Optional[str] = None  # Not required, defaults to None
```


## Testing Your Migration

### Unit Test Updates

```python
import pytest
from pydantic.v1 import ValidationError

def test_model_validation():
    # Test basic validation
    user = User(name="John", age=30)
    assert user.name == "John"
    assert user.age == 30
    
    # Test validation errors
    with pytest.raises(ValidationError):
        User(name="", age=-1)
    
    # Test serialization
    data = user.model_dump()
    assert data == {"name": "John", "age": 30}
    
    # Test JSON serialization
    json_str = user.model_dump_json()
    assert '"name":"John"' in json_str

def test_model_construction():
    # Test model construction
    user = User.model_validate({"name": "John", "age": 30})
    assert isinstance(user, User)
    
    # Test JSON parsing
    json_data = '{"name": "John", "age": 30}'
    user = User.model_validate_json(json_data)
    assert user.name == "John"
```


### Integration Test Considerations

1. **API Serialization**: Test that your API responses still work
2. **Database Integration**: Test ORM integration with `from_attributes=True`
3. **Configuration Loading**: Test environment variable loading
4. **Custom Validators**: Test all custom validation logic
5. **JSON Schema**: Test API documentation generation

## Performance Implications

### Expected Improvements

1. **5-50x faster validation** due to Rust core[2]
2. **Better memory usage** for large datasets
3. **Faster JSON serialization** with compact output
4. **Improved startup times** in v2.11.7

### Potential Regressions

1. **Model construction** may be slower in some cases
2. **Complex regex patterns** may need adjustment
3. **Custom type validation** may need optimization

### Monitoring Migration Performance

```python
import time
from pydantic.v1 import BaseModel

# Benchmark validation
def benchmark_validation(model_class, data, iterations=10000):
    start = time.time()
    for _ in range(iterations):
        model_class.model_validate(data)
    end = time.time()
    return end - start

# Test your models
data = {"name": "John", "age": 30}
time_taken = benchmark_validation(User, data)
print(f"Validation time: {time_taken:.4f} seconds")
```

This comprehensive migration guide covers all major aspects of upgrading from pydantic.v1v1.9.1 to v2.11.7. Each section provides detailed before/after examples, complete with explanations of behavioral changes and best practices for the new version. The migration requires careful attention to detail, but the performance improvements and enhanced features make it worthwhile for most codebases.

