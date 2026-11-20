#!/usr/bin/python3
from __future__ import absolute_import
from __future__ import print_function

import os
import re
import tempfile
import xml.etree.ElementTree as ET

from ansible.module_utils.basic import AnsibleModule


def compile_patterns(module):
    """Turn the patterns argument into (regexp, replacement) pairs."""
    compiled = []
    for index, pattern in enumerate(module.params['patterns']):
        if 'regexp' not in pattern:
            module.fail_json(msg="pattern %d has no 'regexp'" % index)
        regexp = pattern['regexp']
        if not regexp:
            # Nothing was collected for this pattern.  An empty regexp matches
            # at every position, which would pepper the file with the
            # replacement, so skip it.
            continue
        try:
            # re.MULTILINE to match the behaviour of the replace module, whose
            # patterns are reused here.
            compiled.append((re.compile(regexp, re.MULTILINE),
                             pattern.get('replace') or ''))
        except re.error as err:
            # The pattern itself is a secret, so it is never echoed back.
            module.fail_json(msg="pattern %d does not compile: %s" % (index, err))
    return compiled


def redact(value, compiled):
    """Apply every pattern to one string, reporting whether it changed."""
    if not value:
        return value, False
    redacted = value
    for regexp, replacement in compiled:
        redacted = regexp.sub(replacement, redacted)
    return redacted, redacted != value


def redact_tree(tree, compiled):
    """Redact the text and the attribute values of every element."""
    changed = False
    for element in tree.iter():
        element.text, hit = redact(element.text, compiled)
        changed = changed or hit
        element.tail, hit = redact(element.tail, compiled)
        changed = changed or hit
        for name, value in list(element.attrib.items()):
            element.attrib[name], hit = redact(value, compiled)
            changed = changed or hit
    return changed


def parse_with_comments(path):
    """Parse path, keeping the comments and the processing instructions.

    The default parser drops both, so a credential written into a comment
    would be neither redacted nor removed.  Kept as nodes they carry their
    body in .text and are redacted like any other value.  insert_comments
    arrived in Python 3.8; on anything older the comments are dropped as
    before, and the rewrite forced by matches_outside_tree() is what keeps
    them from being uploaded.
    """
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True,
                                                    insert_pis=True))
    except TypeError:
        parser = None
    return ET.parse(path, parser=parser)


def markers_of(compiled):
    """The replacement texts, and their escaped spelling, as written out.

    A marker is not a leak, but it can read like one: with a secret of 'a',
    '<redacted for security>' matches the pattern.  They are blanked before
    a file is searched for anything left over.
    """
    markers = []
    for _, replacement in compiled:
        marker = re.sub(r'\\g<\d+>|\\\d', '', replacement)
        if marker:
            markers.append(marker)
            markers.append(marker.replace('&', '&amp;').replace('<', '&lt;')
                           .replace('>', '&gt;').replace('"', '&quot;'))
    return markers


def still_matches(text, compiled, markers):
    """Does any pattern still match text, ignoring the markers we wrote?"""
    probe = text
    for marker in markers:
        probe = probe.replace(marker, '')
    return any(regexp.search(probe) for regexp, _ in compiled)


def values_match(tree, compiled, markers):
    """Does any pattern still match a value of the tree?

    Only the values are looked at.  Searching the serialised document instead
    would hit the markup - an element or an attribute named 'name' matches a
    secret of 'a' - and send a perfectly good artifact down the plain text
    path that this module exists to avoid.
    """
    for element in tree.iter():
        values = [element.text, element.tail] + list(element.attrib.values())
        for value in values:
            if value and still_matches(value, compiled, markers):
                return True
    return False


def write_tree(module, tree, path):
    """Replace path with the redacted tree, atomically."""
    handle, temp_path = tempfile.mkstemp(dir=os.path.dirname(path))
    os.close(handle)
    try:
        tree.write(temp_path, encoding='utf-8', xml_declaration=True)
    except Exception as err:
        os.unlink(temp_path)
        module.fail_json(msg="could not write the redacted copy of %s: %s" % (path, err))
    module.atomic_move(temp_path, path)


def redact_as_text(module, path, compiled):
    """Fall back for a file that does not parse: redact it as plain text.

    The artifact is broken either way, but a credential in it must not reach
    the control server.
    """
    with open(path, 'rb') as handle:
        original = handle.read().decode('utf-8', 'surrogateescape')
    redacted = original
    for regexp, replacement in compiled:
        redacted = regexp.sub(replacement, redacted)
    if redacted == original or module.check_mode:
        return redacted != original
    handle, temp_path = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(handle, 'wb') as temp_file:
        temp_file.write(redacted.encode('utf-8', 'surrogateescape'))
    module.atomic_move(temp_path, path)
    return True


def main():
    module = AnsibleModule(
        argument_spec=dict(
            path=dict(type='path', required=True),
            patterns=dict(type='list', elements='dict', required=True, no_log=True),
        ),
        supports_check_mode=True,
    )

    path = module.params['path']
    compiled = compile_patterns(module)
    markers = markers_of(compiled)

    try:
        with open(path, 'rb') as handle:
            original = handle.read().decode('utf-8', 'surrogateescape')
        tree = parse_with_comments(path)
    except ET.ParseError as err:
        changed = redact_as_text(module, path, compiled)
        module.exit_json(changed=changed, path=path, well_formed=False,
                         msg="%s is not well formed XML (%s), redacted as plain text" % (path, err))
    except (IOError, OSError) as err:
        module.fail_json(msg="could not read %s: %s" % (path, err))

    changed = redact_tree(tree, compiled)

    # What sits before the root element - a comment there, the DOCTYPE and its
    # internal subset - never reaches the tree and so cannot be redacted.  It
    # does not survive serialisation either, so a file whose raw text still
    # matches has to be written out even when no value in the tree changed.
    if not changed and still_matches(original, compiled, markers):
        changed = True

    if changed and not module.check_mode:
        if values_match(tree, compiled, markers):
            # Nothing should reach this, but an upload must never carry a
            # credential: redact the file as plain text instead.
            redact_as_text(module, path, compiled)
            module.exit_json(changed=True, path=path, well_formed=False,
                             msg="%s still matched after redaction, redacted as plain text" % path)
        write_tree(module, tree, path)

    module.exit_json(changed=changed, path=path, well_formed=True)


if __name__ == '__main__':
    main()
