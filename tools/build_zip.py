"""把插件打成可在 Blender 里直接安装的 zip：dist/stellartoon_mmd-<版本>.zip

用法（任意 Python 3）：python tools/build_zip.py
"""
import ast
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = 'stellartoon_mmd'


def addon_version():
    with open(os.path.join(ROOT, PKG, '__init__.py'), encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'bl_info':
            info = ast.literal_eval(node.value)
            return '.'.join(str(x) for x in info['version'])
    raise RuntimeError('bl_info not found')


def main():
    version = addon_version()
    out_dir = os.path.join(ROOT, 'dist')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f'{PKG}-{version}.zip')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(os.path.join(ROOT, PKG)):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for name in files:
                if name.endswith('.pyc'):
                    continue
                path = os.path.join(base, name)
                z.write(path, os.path.relpath(path, ROOT))
    print(out)


if __name__ == '__main__':
    main()
