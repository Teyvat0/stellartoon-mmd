# 读取 HoyoToon-Assets 导出的游戏材质 JSON（Unity Material dump）
import json
import os
import re

IMAGE_EXTS = ('.png', '.tga', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.dds')

KIND_FACE = 'FACE'
KIND_HAIR = 'HAIR'
KIND_BASE = 'BASE'
KIND_WEAPON = 'WEAPON'

KIND_LABELS = {
    KIND_FACE: '脸',
    KIND_HAIR: '头发',
    KIND_BASE: '身体',
    KIND_WEAPON: '武器',
}

# 不是角色本体卡通材质的 shader，扫描时忽略
_IGNORED_SHADER_WORDS = ('particle', 'stencil', '/ui', 'ui/', 'glassedges', 'spectrum',
                         'liquid', 'starcloak', 'acrylic')


def _pairs_to_dict(value):
    """m_Floats / m_Colors / m_TexEnvs 有两种格式：字典，或 [{Key, Value}] / [{first, second}] 列表。"""
    if isinstance(value, dict):
        return dict(value)
    out = {}
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                k = item.get('Key', item.get('first'))
                v = item.get('Value', item.get('second'))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                k, v = item
            else:
                continue
            if isinstance(k, str):
                out[k] = v
    return out


def _to_color(v):
    if isinstance(v, dict) and 'r' in v:
        return (float(v.get('r', 0)), float(v.get('g', 0)), float(v.get('b', 0)), float(v.get('a', 1)))
    return None


class MaterialData:
    def __init__(self, path):
        self.path = os.path.normpath(path)
        with open(self.path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        if not isinstance(data, dict) or 'm_SavedProperties' not in data:
            raise ValueError('不是 Unity 材质 JSON')
        self.stem = os.path.splitext(os.path.basename(self.path))[0]
        self.name = data.get('m_Name') or self.stem
        shader = data.get('m_Shader') or {}
        self.shader = shader.get('Name', '') if isinstance(shader, dict) else ''
        props = data.get('m_SavedProperties') or {}
        self.floats = {}
        for k, v in _pairs_to_dict(props.get('m_Floats')).items():
            try:
                self.floats[k] = float(v)
            except (TypeError, ValueError):
                pass
        self.colors = {}
        for k, v in _pairs_to_dict(props.get('m_Colors')).items():
            c = _to_color(v)
            if c is not None:
                self.colors[k] = c
        self.textures = {}
        for k, v in _pairs_to_dict(props.get('m_TexEnvs')).items():
            tex = (v or {}).get('m_Texture') if isinstance(v, dict) else None
            if isinstance(tex, dict):
                n = tex.get('Name') or ''
                if n and not tex.get('IsNull', False):
                    self.textures[k] = n

    # ---- 查询 ----
    def get(self, key):
        if key in self.floats:
            return self.floats[key]
        if key in self.colors:
            return self.colors[key]
        return None

    @property
    def main_tex(self):
        return self.textures.get('_MainTex', '')

    @property
    def variant(self):
        m = re.search(r'_([DS])$', self.stem)
        return m.group(1) if m else ''

    @property
    def group_key(self):
        return re.sub(r'_[DS]$', '', self.stem)

    @property
    def kind(self):
        s = self.shader.lower()
        n = self.stem.lower()
        if 'characterface' in s or '_facemap' in {k.lower() for k in self.textures} or n.endswith('_mat_face'):
            return KIND_FACE
        if 'characterhair' in s or '_mat_hair' in n:
            return KIND_HAIR
        if 'weapon' in n:
            return KIND_WEAPON
        return KIND_BASE

    def is_usable(self):
        s = self.shader.lower()
        if any(w in s for w in _IGNORED_SHADER_WORDS):
            return False
        return bool(self.main_tex)


def scan_materials(root):
    """递归扫描目录下的材质 JSON，返回 MaterialData 列表（忽略解析失败和非角色材质）。"""
    found = []
    if not root or not os.path.isdir(root):
        return found
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith('.json'):
                continue
            try:
                md = MaterialData(os.path.join(dirpath, fn))
            except Exception:
                continue
            if md.is_usable():
                found.append(md)
    found.sort(key=lambda m: m.path.lower())
    return found


class TextureIndex:
    """按文件名（不含扩展名，忽略大小写）查找贴图。先加入的目录优先。"""

    def __init__(self):
        self._by_stem = {}
        self._dirs = []

    def add_dir(self, root):
        if not root or not os.path.isdir(root):
            return
        root = os.path.normpath(root)
        if root in self._dirs:
            return
        self._dirs.append(root)
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                stem, ext = os.path.splitext(fn)
                if ext.lower() in IMAGE_EXTS:
                    self._by_stem.setdefault(stem.lower(), os.path.join(dirpath, fn))

    def find(self, name):
        if not name:
            return None
        key = os.path.splitext(name)[0].lower() if os.path.splitext(name)[1].lower() in IMAGE_EXTS else name.lower()
        p = self._by_stem.get(key)
        if p:
            return p
        # 去掉 "#123456" 这类重名后缀再试
        p = self._by_stem.get(re.sub(r'#\d+$', '', key))
        return p

    def find_containing(self, *words):
        words = [w.lower() for w in words]
        for stem, p in self._by_stem.items():
            if all(w in stem for w in words):
                return p
        return None
