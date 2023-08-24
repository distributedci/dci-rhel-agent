## Create a migration file

Create a new python file starting with a number (required). Add an explicit name, it will be used in the output.

Example `0001_add_foo.py` or `0002_add_bar_and_baz.py`

## Add migration operations in your migration file

Your migration file must contain a list of operations.
An operation is a pure python function. It takes the content of the settings file as a dict.
And should return the new settings.

Add an explicit function name because it's used in the check output.

Example:

```python
def operation_1(file_content):
    file_content['bar'] = 'bar'
    return file_content

def operation_2(file_content):
    file_content['baz'] = 'baz'
    return file_content

operations = [operation_1, operation_2]
```

## Check migrations needed

To check if a migration is required, you can call the check command.

```python
from migration import check

check("/tmp/migration_folder", "/tmp/settings.yml")
```

/!\ a valid yaml file is required

It returns a dict with different informations:

```python
{
    "migration_required": True,
    "file_to_migrate": {
        "path": "/tmp/settings.yml",
        "content": "---\ntopic: RHEL-9.2\n...",
        "format": "yaml",
        "parsed_content": {"topic": "RHEL-9.2"},
        "version": 0,
    },
    "file_migrated": {
        "path": "/tmp/settings.yml",
        "content": "# migration_version: 3\ntopic: RHEL-9.2\nfoo: foo\nbar: bar\nbaz: baz\n",
        "format": "yaml",
        "parsed_content": {"topic": "RHEL-9.2", "foo": "foo", "bar": "bar", "baz": "baz"},
        "version": 3,
    },
    "operations": {
        "0001_add_foo.py::operation_1": "OK",
        "0002_add_bar_and_baz.py::operation_1": "OK",
        "0002_add_bar_and_baz.py::operation_2": "OK",
    },
    "has_error": False,
}
```

- `migration_required`: is the migration required or not
- `file_to_migrate`: information about the file that going to be migrated
- `file_migrated`: information about the file that going to be migrated
  - `path`: the path of the file
  - `content`: the content of the file
  - `parsed_content`: the content of the file parsed (python dictionnary)
  - `version`: the migration version read in the file
- `operations`: list of all the operations statuses (`SKIPPED`, `OK`, `ERROR`)
- `has_error`: if an operation failed, an error is displayed.

Operations after an error are skipped.

## Apply the migration (no dry run)

```python
from migration import migrate

migrate("/tmp/migration_folder", "/tmp/settings.yml")
```

It display an information about the migration:

```
Running migrations:
Applying 0001_add_foo.py::operation_1... OK
Applying 0002_add_bar_and_baz.py::operation_1... OK
Applying 0002_add_bar_and_baz.py::operation_2... OK
```
