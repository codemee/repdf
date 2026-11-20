"""Windows executable branding consumed by PyInstaller."""
import re


def version_info_text(version):
    match = re.match(r'\d+(?:\.\d+){0,3}', version)
    if not match:
        raise ValueError(f'Invalid version: {version}')
    numbers = tuple(map(int, match.group().split('.')))
    numbers += (0,) * (4 - len(numbers))
    if any(n > 65535 for n in numbers):
        raise ValueError(f'Windows version component too large: {version}')
    strings = {'FileDescription': 'RePDF', 'ProductName': 'RePDF',
               'InternalName': 'RePDF', 'OriginalFilename': 'repdf.exe',
               'FileVersion': version, 'ProductVersion': version}
    entries = ',\n'.join(f'StringStruct({key!r}, {value!r})' for key, value in strings.items())
    return f'''VSVersionInfo(
 ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r},
 mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
 kids=[StringFileInfo([StringTable('040904B0', [{entries}])]),
 VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''
