from migrations import (
    _filter_and_order_migrations_files,
    _list_file_path_in,
    migrate,
    check,
    _extract_operations,
    _apply_operations,
    _get_migration_version,
)


def test_filter_and_order_migrations_files():
    list_of_files = [
        "0002_second_migration.py",
        "README.md",
        "0004_not_a_python_file",
        "0001_first_migration.py",
        "0003_third_migration_file.py",
        "0005_last_one.py",
    ]
    ordered_migrations_files = [
        "0001_first_migration.py",
        "0002_second_migration.py",
        "0003_third_migration_file.py",
        "0005_last_one.py",
    ]
    assert _filter_and_order_migrations_files(list_of_files) == ordered_migrations_files


def test_list_file_path_in(tmpdir):
    tmpdir.join("0002_second_migration.py").write("")
    tmpdir.join("README.md").write("")
    tmpdir.join("0004_not_a_python_file").write("")
    tmpdir.join("0001_first_migration.py").write("")
    tmpdir.join("0003_third_migration_file.py").write("")
    tmpdir.join("0005_last_one.py").write("")
    assert _list_file_path_in(str(tmpdir)) == [
        "0002_second_migration.py",
        "README.md",
        "0004_not_a_python_file",
        "0001_first_migration.py",
        "0003_third_migration_file.py",
        "0005_last_one.py",
    ]


def test_operations_extractor():
    content = "def operation_1(file_content):\n    return file_content[::-1]\noperations = [operation_1]"
    operations = _extract_operations("file_name", content)
    assert len(operations) == 1
    assert operations[0].__name__ == "file_name::operation_1"
    assert operations[0]("abc") == "cba"


def test_apply_operations():
    def operation_1(file_content):
        file_content["foo"] = "foo"
        return file_content

    def operation_2(file_content):
        file_content["bar"] = "bar"
        return file_content

    file_content = {}
    migration_version = 0
    assert _apply_operations(
        [operation_1, operation_2], file_content, migration_version
    ) == {
        "migration_required": True,
        "content": {"foo": "foo", "bar": "bar"},
        "new_version": 2,
        "operations": {"operation_1": "OK", "operation_2": "OK"},
        "has_error": False,
    }


def test_apply_an_operation_that_raises_an_exception_stop_at_previous_operation():
    def operation_1(file_content):
        file_content["foo"] = "foo"
        return file_content

    def operation_2(file_content):
        raise Exception()

    file_content = {}
    migration_version = 0
    assert _apply_operations(
        [operation_1, operation_2], file_content, migration_version
    ) == {
        "migration_required": True,
        "content": {"foo": "foo"},
        "new_version": 1,
        "operations": {"operation_1": "OK", "operation_2": "ERROR"},
        "has_error": True,
    }


def test_apply_an_operation_with_skipped_operations():
    def operation_1(file_content):
        file_content["foo"] = "foo"
        return file_content

    def operation_2(file_content):
        raise Exception()

    def operation_3(file_content):
        file_content["baz"] = "baz"
        return file_content

    file_content = {"foo": "foo"}
    migration_version = 1
    assert _apply_operations(
        [operation_1, operation_2, operation_3], file_content, migration_version
    ) == {
        "migration_required": True,
        "content": {"foo": "foo"},
        "new_version": 1,
        "operations": {
            "operation_1": "SKIPPED",
            "operation_2": "ERROR",
            "operation_3": "SKIPPED",
        },
        "has_error": True,
    }


def test_migration_required_with_applied_migrations():
    def operation_1(file_content):
        return file_content

    def operation_2(file_content):
        return file_content

    file_content = {}
    migration_version = 2
    assert _apply_operations(
        [operation_1, operation_2], file_content, migration_version
    ) == {
        "migration_required": False,
        "content": {},
        "new_version": 2,
        "operations": {
            "operation_1": "SKIPPED",
            "operation_2": "SKIPPED",
        },
        "has_error": False,
    }


def test_get_migration_version_return_version_0_if_no_migration_version(tmpdir):
    settings_file = tmpdir.join("settings.yml")
    settings_file.write("---\nfoo: foo\n")
    assert _get_migration_version(str(settings_file)) == 0


def test_get_migration_version_return_migration_version(tmpdir):
    settings_file = tmpdir.join("settings.yml")
    settings_file.write("# migration_version: 1\nfoo: foo\n")
    assert _get_migration_version(str(settings_file)) == 1


def test_get_migration_version_return_migration_version_even_if_not_in_first_line(
    tmpdir,
):
    settings_file = tmpdir.join("settings.yml")
    settings_file.write("\nfoo: foo\n# migration_version: 2\nbar: bar\n")
    assert _get_migration_version(str(settings_file)) == 2


def test_migrate(tmpdir):

    migrations_folder = tmpdir.mkdir("migrations_folder")
    migrations_folder.join("0002_add_bar.py").write(
        "def operation(file_content):\n    file_content['bar'] = 'bar'\n    return file_content\noperations = [operation]"
    )
    migrations_folder.join("0001_add_foo.py").write(
        "def operation(file_content):\n    file_content['foo'] = 'foo'\n    return file_content\noperations = [operation]"
    )

    settings_folder = tmpdir.mkdir("settings_folder")
    settings_file = settings_folder.join("settings.yml")
    settings_file.write("---\ntopic: RHEL-9.2\n...")

    migrate(str(migrations_folder), str(settings_file))

    with open(settings_file) as f:
        assert (
            f.read() == "# migration_version: 2\ntopic: RHEL-9.2\nfoo: foo\nbar: bar\n"
        )


def test_migrate_with_exception_stop(tmpdir):

    migrations_folder = tmpdir.mkdir("migrations_folder")
    migrations_folder.join("0002_add_bar.py").write(
        "def operation(file_content):\n    raise\noperations = [operation]"
    )
    migrations_folder.join("0001_add_foo.py").write(
        "def operation(file_content):\n    file_content['foo'] = 'foo'\n    return file_content\noperations = [operation]"
    )

    settings_folder = tmpdir.mkdir("settings_folder")
    settings_file = settings_folder.join("settings.yml")
    settings_file.write("---\ntopic: RHEL-9.2\n...")

    migrate(str(migrations_folder), str(settings_file))

    with open(settings_file) as f:
        assert f.read() == "# migration_version: 1\ntopic: RHEL-9.2\nfoo: foo\n"


def test_if_first_operation_fails_do_not_write_migration_version_0_in_settings_file(
    tmpdir,
):

    migrations_folder = tmpdir.mkdir("migrations_folder")
    migrations_folder.join("0001_add_foo.py").write(
        "def operation(file_content):\n    raise\noperations = [operation]"
    )

    settings_folder = tmpdir.mkdir("settings_folder")
    settings_file = settings_folder.join("settings.yml")
    settings_file.write("---\ntopic: RHEL-9.2\n...")

    migrate(str(migrations_folder), str(settings_file))

    with open(settings_file) as f:
        assert f.read() == "topic: RHEL-9.2\n"


def test_skip_already_applied_migration(tmpdir):

    migrations_folder = tmpdir.mkdir("migrations_folder")
    migrations_folder.join("0002_add_bar.py").write(
        "def operation(file_content):\n    file_content['bar'] = 'bar'\n    return file_content\noperations = [operation]"
    )
    migrations_folder.join("0001_add_foo.py").write(
        "def operation(file_content):\n    file_content['foo'] = 'foo'\n    return file_content\noperations = [operation]"
    )

    settings_folder = tmpdir.mkdir("settings_folder")
    settings_file = settings_folder.join("settings.yml")
    settings_file.write("# migration_version: 1\ntopic: RHEL-9.2\nfoo: changed\n")

    migrate(str(migrations_folder), str(settings_file))

    with open(settings_file) as f:
        assert (
            f.read()
            == "# migration_version: 2\ntopic: RHEL-9.2\nfoo: changed\nbar: bar\n"
        )


def test_check_apply_dry_run_and_returns_information_about_the_migration(
    tmpdir,
):

    migrations_folder = tmpdir.mkdir("migrations_folder")
    migrations_folder.join("0002_add_bar_and_baz.py").write(
        "def operation_2(file_content):\n    file_content['baz'] = 'baz'\n    return file_content\ndef operation_1(file_content):\n    file_content['bar'] = 'bar'\n    return file_content\noperations = [operation_1, operation_2]"
    )
    migrations_folder.join("0001_add_foo.py").write(
        "def operation_1(file_content):\n    file_content['foo'] = 'foo'\n    return file_content\noperations = [operation_1]"
    )

    settings_folder = tmpdir.mkdir("settings_folder")
    settings_file = settings_folder.join("settings.yml")
    settings_file.write("---\ntopic: RHEL-9.2\n...")

    assert check(str(migrations_folder), str(settings_file)) == {
        "migration_required": True,
        "content": {"topic": "RHEL-9.2", "foo": "foo", "bar": "bar", "baz": "baz"},
        "new_version": 3,
        "operations": {
            "0001_add_foo.py::operation_1": "OK",
            "0002_add_bar_and_baz.py::operation_1": "OK",
            "0002_add_bar_and_baz.py::operation_2": "OK",
        },
        "has_error": False,
    }


def test_check_migration_needed(
    tmpdir,
):
    migrations_folder = tmpdir.mkdir("migrations_folder")
    settings_folder = tmpdir.mkdir("settings_folder")
    settings_file = settings_folder.join("settings.yml")
    settings_file.write("---\ntopic: RHEL-9.2\n...")

    assert check(str(migrations_folder), str(settings_file)) == {
        "migration_required": False,
        "content": {"topic": "RHEL-9.2"},
        "new_version": 0,
        "operations": {},
        "has_error": False,
    }
