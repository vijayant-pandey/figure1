# Coding Standards

### Reviewer Responsibilities

For each of the sections, there are some specific guidelines laid out for reviewers to follow. These are generally kept
vague since the primary expectation is that reviewers use their best judgement.

In general, if you have a difficult time following the code, ask the coder for clarification. It is ideal that the code
should be easy to understand, if it isn't, this is likely an improvement that can be made.
Variables should be named in a way that makes it easy to understand what they represent, and errors should be raised as
exceptions. Functions should be short and queries should be as simple as possible.

### Coder Responsibilities

Before you submit your code for review, go over it as a reviewer to try to find areas where you can improve. It should
pass your review before you pass it to someone else. This is intended to ensure that the reviewer can focus on more
significant issues that might otherwise get lost.

### Formatting

When tests are run, pycodestyle is run against the code. At a minimum, any code committed must pass this. The
configuration is in tox.ini in the [pycodestyle] section.

### Functions

Not every function needs to be documented, however the entrypoint to a flow should be documented and every function
should have an expected return type.

In many cases, it makes sense to have some additional documentation in other functions through the flow, especially if
a function is accessed from many other flows.

The documentation is reStructured style, it looks like this:

```
    """
    Returns a list of open change request entries
    :param change_opened: Timedelta object indicating the most recent change request to look for. This is to avoid
        returning change requests that may be in use by the user.
    :param session: Database session
    :type session: Session
    :param has_verification_type: If VerificationType is set, then return all open change requests of this type. If it
        None, then return open change requests that have no type.
    :type has_verification_type: VerificationType
    :return:
    """
```

The return type can be documented either by using arrow notation ``def some_function() -> Optional[str]`` or by using
rtype as shown below. Both are equivalent

```
"""
Function documentation...

:rtype: Optional[str]
```

It should also be noted that the ``:type <param name>:`` shown above is equivilent to typing in the function params like
this ``def some_function(session: Session)``. Including both is redundant.

#### Function Scope

Functions in general should do one thing, utility functions are encouraged to be used rather than including in the main
function

#### *Review Requirements*

The minimum requirement is to have a flow documented at the start, including variables and what exceptions can be
thrown.

Function scope should be judged by the reviewer.

### Classes

Since python is object-oriented, classes are used heavily. Inside a class, there are two forms of self-reference and one
that eliminates self-reference. A normal class method with no decorator takes self as an argument, this is the most
common. The self argument refers to one instantiated instance of a class. In order to call this method, you must
instantiate the class first, this isn't free, though this depends on how heavy the ``__init__`` method is.

```python
class AClass:
    def my_method(self):
        pass


a = AClass()
a.my_method()
```

Another approach is using a class method, a class method does not refer to as instantiated instance, but to the base
class instance. This means that any other instance created from this class will have access to these variables. This
allows for some caching within the thread, but this should not be relied on.

```python
class AClass:
    my_class_var = None

    @classmethod
    def my_class_method(cls):
        cls.my_class_var = 'this'

    def my_method(self):
        return self.my_class_var


AClass.my_class_method()
a = AClass()
a.my_method()

```

Finally, we can use the staticmethod approach, static methods can be accessed without instantiating the class.
Essentially they act as a way to group functions since functions decorated like this have no access to the class

```python
class AClass:

    @staticmethod
    def my_method():
        pass


AClass.my_method()
```

#### What to use?

In general, classmethods are not commonly used. The most common ones are the first ones since they are the easiest to
understand, however we use the staticmethod approach quite heavily within our codebase. Ultimately the best approach
depends on what you are trying to do, staticmethods are nice to group a set of functions that are related, but don't
need to share data for example.

#### *Review Requirements*

In general, the lightest approach should be used. Static classes are good for grouping functions together into class
where no data needs to be shared but where they share a common purpose. If data is shared, but it rarely changes, then
using a classmethod implementation works well. For classes that share data frequently between functions, the default
class method should be used.

There isn't one way that is correct here, the important part is that the coder can explain the approach taken to the
reviewer.

### Imports

**Note** Many older files do not conform to these standards, if you are working on a file like this, please ensure it
conforms as part of your PR.

In terms of formatting, imports should always be on a new line, for example:

```
from figure1.common.models import something
from figure1.common.models import somthing2
```

Assuming you are using a jetbrains IDE, you can import code_standards.xml from the root directory of the repository.

For imports, you will be able to run Optimize Imports on a file that does not conform to have the IDE fix it up for you.

#### *Review Requirements*

Imports must have one line per import as shown above.

## Pydantic Models

Documenting pydantic is out of scope, but https://pydantic-docs.helpmanual.io/ should be referred to often.

However, when creating models, most fields should use Optional[] which is shorthand for ``Union[str, None]`` where str
is the expected type for the field.

### ORM

We use pydantic models heavily to serialize ORM instances, there are some standards that should be followed. On the
database side, column names are underscore separated or snake_case, however pydantic field names are camelCase.
As a result when creating a pydantic model to serialize an orm instance, it is necessary to use a field alias

```
MyModel(BaseModel)
userUuid: Optional[str] = Field(alias='user_uuid')
```

This approach allows for some variation that has crept in over time.

### Validation Models

New endpoints should use pydantic model to validate incoming data, by default, a validation error will raise a 422.

#### *Review Requirements*

Pydantic models should use Optional in most places, places where it is not used should be explained by the coder.

Pydantic field names should be camelCase, exceptions should be explained by the coder.

Pydantic types should be constrained.

Validators should only do one thing. Exceptions are root validators, however these should be used sparingly.

## Modules

When deciding if a piece of code should be in a new module or not, think about how independent it is. A top level
module, that is to say, one under figure1, should have an independent function that is used by many other parts of the
code, but does not depend directly on any of them.
If the module is second level, like one under figure1.pro for example, the module should contribute an independant part
to the module, at this level you could import from another module at the same level if needed.

To generalize this, a module should try to contain a function that is independent at the level it is at.

#### *Review Requirements*

This is largely up to the judgement of the coder, however it is advisable to err on the side of creating new modules.

## Testing

When creating tests, try to create tests that are composed of independent parts. Use pytest fixtures for this, using
yield to control the teardown.

In the existing tests, endpoints are used to test the full flow of a given function, but when composing tests, this
isn't always the best approach. It is better to start from the core function and work your way out, but this may not
always be feasible.

#### *Review Requirements*

Tests should be as narrow as possible and should create necessary data using fixtures.

Tests should avoid committing where possible.

### Models

New models should have a functional test which independent data to ensure they create the expected output.

## Imports

Ensure the new packages are always added to the requirements.txt file.

### Avoiding circular imports

When importing in python, it is important to avoid circular imports. For that reason, there are some packages where you
should never import to from other packages inside figure1. In general, this means that you should never 'import down'
which means you should not import from a package above where you are. There are exceptions to this, but it is a general
rule to keep in mind. There are also some specific rules to keep in mind.

```
figure1.common.types should avoid importing from anywhere in figure1
figure1.common.models.db can import from figure1.common.types, and from figure1.core but nowhere else.
figure1.pro should not be imported to anywhere else except for figure1.run

```
