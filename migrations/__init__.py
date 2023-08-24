import typing
import yaml

from os import listdir
from os.path import isfile, join
from copy import deepcopy

Operation = typing.Callable
OperationList = typing.List[Operation]


_VERSION_STRING = "# migration_version:"


def _extract_operations(filename: str, file_content: str) -> OperationList:
    operations = []

    exec_globals = {}
    exec(file_content, exec_globals)

    if "operations" in exec_globals and isinstance(exec_globals["operations"], list):
        for operation in exec_globals["operations"]:
            if callable(operation):
                operation.__name__ = f"{filename}::{operation.__name__}"
                operations.append(operation)

    return operations


def _read_file_to_migrate(file_to_migrate: str) -> typing.Dict:
    with open(file_to_migrate, "r") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(e)


def _filter_and_order_migrations_files(
    list_of_files: typing.List[str],
) -> typing.List[str]:
    only_python_files = [f for f in list_of_files if f.endswith(".py")]
    return sorted(
        only_python_files, key=lambda migration_file: int(migration_file.split("_")[0])
    )


def _list_file_path_in(folder: str):
    return [f for f in listdir(folder) if isfile(join(folder, f))]


def _get_all_operations(migration_folder: str):
    ordered_migration_files = _filter_and_order_migrations_files(
        _list_file_path_in(migration_folder)
    )
    operations = []
    for migration_file in ordered_migration_files:
        file_path = join(migration_folder, migration_file)
        with open(file_path) as f:
            operations += _extract_operations(migration_file, f.read())
    return operations


def _get_migration_version(file_to_migrate):
    version = 0
    with open(file_to_migrate, "r") as f:
        try:
            for line in f.readlines():
                if _VERSION_STRING in line:
                    version = int(line.split(_VERSION_STRING)[-1].strip())
                    break
        except:
            pass
    return version


def _apply_operations(operations: OperationList, input: typing.Dict, version=int):
    output = deepcopy(input)
    new_version = version
    operations_statuses = {}
    has_error = False
    for i, operation in enumerate(operations):
        if i < version or has_error:
            operations_statuses[operation.__name__] = "SKIPPED"
            continue
        try:
            output = operation(output)
            operations_statuses[operation.__name__] = "OK"
            new_version += 1
        except Exception:
            operations_statuses[operation.__name__] = "ERROR"
            has_error = True
    return {
        "migration_required": len(operations) > version,
        "content": output,
        "new_version": new_version,
        "operations": operations_statuses,
        "has_error": has_error,
    }


def _dry_run(migration_folder: str, file_to_migrate: str):
    operations = _get_all_operations(migration_folder)
    content_to_migrate = _read_file_to_migrate(file_to_migrate)
    current_version = _get_migration_version(file_to_migrate)

    return _apply_operations(operations, content_to_migrate, current_version)


def _update_file_to_migrate(
    file_to_migrate: str, content: typing.Dict, new_version: int
):
    with open(file_to_migrate, "w") as f:
        try:
            if new_version > 0:
                f.write(f"{_VERSION_STRING} {new_version}\n")
            f.write(yaml.dump(content, sort_keys=False))
        except yaml.YAMLError as e:
            print(e)


def migrate(migration_folder: str, file_to_migrate: str):
    application = _dry_run(migration_folder, file_to_migrate)

    stdout = "Running migrations:\n"
    for operation_name, status in application["operations"].items():
        stdout += f"Applying {operation_name}... {status}\n"
    if application["migration_required"] == False:
        stdout += "No migration to apply\n"

    print(stdout)

    _update_file_to_migrate(
        file_to_migrate, application["content"], application["new_version"]
    )


def check(migration_folder: str, file_to_migrate: str):
    return _dry_run(migration_folder, file_to_migrate)
