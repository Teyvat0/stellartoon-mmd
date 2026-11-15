# MMD 材质 ↔ 游戏材质 自动匹配
import os

import bpy

try:
    import numpy as np
except ImportError:  # Blender 自带 numpy，这里只是保险
    np = None

THUMB = 32
# 平均绝对色差（0~1）低于此值视为同一张贴图
MATCH_THRESHOLD = 0.06
LOOSE_THRESHOLD = 0.25   # 改过色的贴图：足够像、比第二名明显更像、像素尺寸一致
LOOSE_MARGIN = 1.4

NO_OUTLINE_WORDS = ('目', '瞳', '眼', '睛', 'eye', 'ハイライト', '齒', '齿', '牙', '歯', '舌',
                    'tooth', 'teeth', 'tongue', '白目', '目光', '高光')

_thumb_cache = {}


def mmd_root_of(obj):
    o = obj
    while o is not None:
        if getattr(o, 'mmd_type', '') == 'ROOT':
            return o
        o = o.parent
    return None


def find_armature(obj):
    """从当前选中物体找到模型骨架。"""
    if obj is None:
        return None
    if obj.type == 'ARMATURE':
        return obj
    root = mmd_root_of(obj)
    if root:
        for c in root.children_recursive if hasattr(root, 'children_recursive') else root.children:
            if c.type == 'ARMATURE':
                return c
    if obj.type == 'MESH':
        for m in obj.modifiers:
            if m.type == 'ARMATURE' and m.object:
                return m.object
        if obj.parent and obj.parent.type == 'ARMATURE':
            return obj.parent
    return None


def model_meshes(arm):
    """骨架驱动的所有网格（子物体或带该骨架修改器的网格）。"""
    out = []
    for o in bpy.data.objects:
        if o.type != 'MESH':
            continue
        if o.parent == arm or any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers):
            out.append(o)
    out.sort(key=lambda o: o.name)
    return out


def mmd_display_name(mat):
    mm = getattr(mat, 'mmd_material', None)
    n = getattr(mm, 'name_j', '') if mm else ''
    return n or mat.name


def base_texture_path(mat):
    """MMD 材质的主贴图文件路径。mmd_tools 的节点名是 mmd_base_tex。"""
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None
    nodes = mat.node_tree.nodes
    cand = [nodes.get('mmd_base_tex')] + [n for n in nodes if n.type == 'TEX_IMAGE']
    for n in cand:
        if n and getattr(n, 'image', None):
            img = n.image
            p = bpy.path.abspath(img.filepath, library=img.library) if img.filepath else ''
            if p and os.path.isfile(p):
                return os.path.normpath(p)
    return None


def _thumbnail(path):
    if np is None or not path or not os.path.isfile(path):
        return None
    key = (path, os.path.getmtime(path))
    if key in _thumb_cache:
        return _thumb_cache[key]
    img = None
    try:
        img = bpy.data.images.load(path, check_existing=False)
        w, h = img.size
        if w == 0 or h == 0:
            raise RuntimeError('empty')
        img.scale(THUMB, THUMB)
        buf = np.empty(THUMB * THUMB * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        res = (buf.reshape(THUMB, THUMB, 4)[:, :, :3].copy(), w / h, (w, h))
    except Exception:
        res = None
    finally:
        if img is not None:
            bpy.data.images.remove(img)
    _thumb_cache[key] = res
    return res


def texture_distance(path_a, path_b):
    """两张贴图的差异：0 完全相同，越大越不像。读不到返回 None。"""
    if path_a and path_b and os.path.normcase(path_a) == os.path.normcase(path_b):
        return 0.0
    a = _thumbnail(path_a)
    b = _thumbnail(path_b)
    if a is None or b is None:
        return None
    d = float(np.abs(a[0] - b[0]).mean())
    if abs(a[1] - b[1]) > 0.01:
        d += 1.0
    return d


def same_pixel_size(path_a, path_b):
    a = _thumbnail(path_a)
    b = _thumbnail(path_b)
    return a is not None and b is not None and a[2] == b[2]


def pick_match(src, candidates):
    """candidates: [(game_tex_path, data)]。返回 (data, distance, confident) 或 (None, best_d, False)。
    MMD 作者常会改贴图（加腮红、调色），所以除了严格阈值，还接受“明显最像、尺寸一致”的候选。"""
    scored = []
    for tp, md in candidates:
        d = texture_distance(src, tp)
        if d is not None:
            scored.append((d, tp, md))
    if not scored:
        return None, None, False
    scored.sort(key=lambda x: x[0])
    d0, tp0, md0 = scored[0]
    if d0 <= MATCH_THRESHOLD:
        return md0, d0, True
    d1 = scored[1][0] if len(scored) > 1 else 9.0
    if d0 <= LOOSE_THRESHOLD and d1 >= d0 * LOOSE_MARGIN and same_pixel_size(src, tp0):
        return md0, d0, False
    return None, d0, False


def wants_outline(mat):
    n = (mmd_display_name(mat) + ' ' + mat.name).lower()
    return not any(w.lower() in n for w in NO_OUTLINE_WORDS)


def collect_materials(meshes):
    seen = []
    for o in meshes:
        for slot in o.material_slots:
            m = slot.material
            if m and m not in seen and not m.get('stmmd_char'):
                seen.append(m)
    return seen
