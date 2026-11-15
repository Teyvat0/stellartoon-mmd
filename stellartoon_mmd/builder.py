# 把 StellarToon 模板挂到 MMD 模型上
import json
import math
import os

import bpy
from mathutils import Matrix, Vector

from .json_data import KIND_BASE, KIND_FACE, KIND_HAIR, KIND_WEAPON

TPL_TAG = 'stmmd_tpl'          # 模板数据块上的标记
CHAR_TAG = 'stmmd_char'        # 生成数据块上的角色名标记
ORIG_TAG = 'stmmd_orig'        # 网格上记录原始材质
MOD_LV = 'STMMD Light Vectors'
MOD_OL = 'STMMD Outlines'

TPL_MATERIALS = {
    KIND_BASE: 'StellarToon - Base',
    KIND_HAIR: 'StellarToon - Hair',
    KIND_FACE: 'StellarToon - Face',
    KIND_WEAPON: 'StellarToon - Weapon',
}
GN_LIGHT = 'Light Vectors'
GN_OUTLINE = 'StellarToon - Outlines GN'
REQUIRED_GROUPS = ('StellarToon - Base', 'StellarToon - Hair', 'StellarToon - Face',
                   'StellarToon - Outlines', GN_LIGHT, GN_OUTLINE)

TEX_PREFIX = {KIND_BASE: 'Body', KIND_HAIR: 'Hair', KIND_WEAPON: 'Weapon'}

# ---- JSON 字段 → 节点输入（参考 Character Setup Wizard 的 StellarToon_MaterialDataApplier，
#      并按爻光/飞霄工程里作者实际填写的值补充）。每项: (节点输入名, [候选 JSON 字段，按顺序取第一个存在的])
BASE_MAP = []
for _i in range(8):
    BASE_MAP += [
        (f'Specular Color {_i + 1}', [f'_SpecularColor{_i}']),
        (f'Specular Shininess {_i + 1}', [f'_SpecularShininess{_i}']),
        (f'Specular Roughness {_i + 1}', [f'_SpecularRoughness{_i}']),
        (f'Specular Intensity {_i + 1}', [f'_SpecularIntensity{_i}']),
    ]
BASE_MAP += [
    ('Stockings Color', ['_Stockcolor']),
    ('Stockings Darkened Color', ['_StockDarkcolor']),
    ('Stockings Rim Width', ['_StockDarkWidth']),
    ('Stockings Power', ['_Stockpower']),
    ('Stockings Lighted Width', ['_Stockpower1']),
    ('Stockings Lighted Intensity', ['_StockSP']),
    ('Stockings Texture Intensity', ['_StockRoughness']),
    ('Stockings Thickness', ['_Stockthickness']),
    ('Emission Threshold', ['_EmissionThreshold']),
    ('Emission Intensity', ['_EmissionIntensity']),
    ('Emission Tint Color', ['_EmissionTintColor']),
    ('Tint', ['_RimColor0']),
    ('Thickness', ['_RimWidth']),
]
HAIR_MAP = [
    ('Specular Color', ['_SpecularColor0', '_SpecularColor']),
    ('Specular Shininess', ['_SpecularShininess', '_SpecularShininess0']),
    ('Specular Roughness', ['_SpecularRoughness', '_SpecularRoughness0']),
    ('Specular Intensity', ['_SpecularIntensity', '_SpecularIntensity0']),
    ('Specular Shadow Offset', ['_SpecularShadowOffset']),
    ('Specular Shadow Intensity', ['_SpecularShadowIntensity']),
    ('Emission Threshold', ['_EmissionThreshold']),
    ('Emission Intensity', ['_EmissionIntensity']),
    ('Emission Tint Color', ['_EmissionTintColor']),
    ('Tint', ['_RimColor0']),
    ('Thickness', ['_RimWidth']),
]
FACE_MAP = [
    ('Eye Shadow Color', ['_EyeShadowColor']),
    ('Warm Shadow Color', ['_ShadowColor']),
    ('Cool Shadow Color', ['_DarkColor']),
    ('Nose Line Color', ['_NoseLineColor']),
    ('Nose Line Power', ['_NoseLinePower']),
    ('Emission Threshold', ['_EmissionThreshold']),
    ('Emission Intensity', ['_EmissionIntensity']),
    ('Expression Cheek Color', ['_ExCheekColor']),
    ('Expression Shy Color', ['_ExShyColor']),
    ('Expression Shadow Color', ['_ExShadowColor']),
    ('Expression Eye Color', ['_ExEyeColor']),
    ('Expression Map Threshold', ['_ExMapThreshold']),
]
PARAM_MAPS = {KIND_BASE: BASE_MAP, KIND_WEAPON: BASE_MAP, KIND_HAIR: HAIR_MAP, KIND_FACE: FACE_MAP}


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- 模板
def template_status(path):
    """检查模板文件，返回 (ok, 缺失项列表)。"""
    if not path or not os.path.isfile(path):
        return False, ['模板文件不存在']
    with bpy.data.libraries.load(path, link=False) as (src, _dst):
        mats = set(src.materials)
        groups = set(src.node_groups)
    missing = [n for n in TPL_MATERIALS.values() if n not in mats]
    missing += [n for n in REQUIRED_GROUPS if n not in groups]
    return not missing, missing


def _find_tagged(coll, tag_value):
    for d in coll:
        if d.get(TPL_TAG) == tag_value:
            return d
    return None


def load_template(path):
    """把模板材质与几何节点追加进当前文件（只追加一次），返回 {标记: 数据块}。"""
    want_mats = list(TPL_MATERIALS.values()) + [n + ' Outlines' for n in TPL_MATERIALS.values()]
    want_groups = [GN_LIGHT, GN_OUTLINE]
    result = {}
    missing = [n for n in want_mats if not _find_tagged(bpy.data.materials, n)]
    missing_g = [n for n in want_groups if not _find_tagged(bpy.data.node_groups, n)]
    if missing or missing_g:
        ok, miss = template_status(path)
        if not ok:
            raise BuildError('模板缺少: ' + ', '.join(miss))
        before_m = set(bpy.data.materials)
        before_g = set(bpy.data.node_groups)
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.materials = [n for n in missing if n in src.materials]
            dst.node_groups = [n for n in missing_g if n in src.node_groups]
        for m, n in zip(dst.materials, [n for n in missing if n in src.materials]):
            if m is None:
                continue
            m[TPL_TAG] = n
            m.use_fake_user = True
            m.name = '[STMMD模板] ' + n
        for g, n in zip(dst.node_groups, [n for n in missing_g if n in src.node_groups]):
            if g is None:
                continue
            g[TPL_TAG] = n
            g.use_fake_user = True
        # 模板材质带进来的子节点组也打上 fake user，避免保存时丢失
        for g in set(bpy.data.node_groups) - before_g:
            g.use_fake_user = True
        del before_m
    for n in want_mats:
        result[n] = _find_tagged(bpy.data.materials, n)
    for n in want_groups:
        result[n] = _find_tagged(bpy.data.node_groups, n)
    if any(v is None for v in result.values()):
        raise BuildError('模板追加失败: ' + ', '.join(k for k, v in result.items() if v is None))
    return result


# ---------------------------------------------------------------- 工具函数
def _load_image(path, non_color):
    if not path:
        return None
    img = bpy.data.images.load(path, check_existing=True)
    try:
        img.colorspace_settings.name = 'Non-Color' if non_color else 'sRGB'
    except TypeError:
        pass
    img.alpha_mode = 'CHANNEL_PACKED'
    return img


def _main_group_node(mat):
    nt = mat.node_tree
    n = nt.nodes.get('Group.006')
    if n and n.type == 'GROUP' and n.node_tree:
        return n
    for n in nt.nodes:
        if n.type == 'GROUP' and n.node_tree and n.node_tree.name.startswith('StellarToon - '):
            return n
    return None


def _set_socket(sock, value):
    t = sock.type
    try:
        if t == 'RGBA':
            if isinstance(value, tuple):
                sock.default_value = value
        elif t in ('VALUE', 'INT'):
            if not isinstance(value, tuple):
                sock.default_value = value if t == 'VALUE' else int(round(value))
        elif t == 'BOOLEAN':
            if not isinstance(value, tuple):
                sock.default_value = bool(value)
        elif t == 'VECTOR' and isinstance(value, tuple):
            sock.default_value = value[:len(sock.default_value)]
    except Exception:
        return False
    return True


def set_input(node, name, value, index=0):
    socks = [s for s in node.inputs if s.name == name]
    if len(socks) <= index:
        return False
    return _set_socket(socks[index], value)


def apply_params(node, md, kind):
    applied = 0
    for sock_name, keys in PARAM_MAPS[kind]:
        value = None
        for k in keys:
            value = md.get(k)
            if value is not None:
                break
        if value is None:
            continue
        # 基础着色器里有两个同名的 "Stockings Color"，参数写第二个（第一个连着贴图）
        idx = 1 if sock_name == 'Stockings Color' and sum(1 for s in node.inputs if s.name == sock_name) > 1 else 0
        if set_input(node, sock_name, value, idx):
            applied += 1
    return applied


def _group_image_node(group):
    for n in group.nodes:
        if n.type == 'TEX_IMAGE':
            return n
    return None


def _texture_role(group_name):
    """装贴图的子节点组 → 用哪张图。"""
    if 'Warm Shadow Ramp' in group_name or group_name.startswith('Weapon Shadow Ramp'):
        return 'warm'
    if 'Cool Shadow Ramp' in group_name:
        return 'cool'
    if group_name.startswith('Face Lightmap'):
        return 'facemap'
    if group_name == 'Stockings':
        return 'stock'
    return None


def _src_name(group):
    return group.get('stmmd_src', group.name)


def _needs_local(group, seen=None):
    """节点组本身或其内部（递归）是否含有需要按材质换图的子节点组。"""
    seen = seen if seen is not None else set()
    if group.name in seen:
        return False
    seen.add(group.name)
    if _texture_role(_src_name(group)):
        return True
    for n in group.nodes:
        if n.type == 'GROUP' and n.node_tree and _needs_local(n.node_tree, seen):
            return True
    return False


def _localize_tree(tree, images, tag, copies):
    """把 tree 里含贴图的节点组（任意深度）复制成本材质专用，并填入贴图。copies: {原名: 副本}。"""
    for n in tree.nodes:
        if n.type != 'GROUP' or not n.node_tree:
            continue
        g = n.node_tree
        if g.bl_idname != 'ShaderNodeTree' or not _needs_local(g):
            continue
        base = _src_name(g)
        local = copies.get(base)
        if local is None:
            if g.get('stmmd_owner') == tag:
                local = g
            else:
                local = bpy.data.node_groups.get(f'{base} - {tag}')
                if local is None or local.get('stmmd_owner') != tag:
                    local = g.copy()
                    local.name = f'{base} - {tag}'
                local['stmmd_src'] = base
                local['stmmd_owner'] = tag
                local[CHAR_TAG] = tag.split(':', 1)[0]
                local.use_fake_user = False
            copies[base] = local
            role = _texture_role(base)
            if role:
                tex = _group_image_node(local)
                if tex is not None and (images.get(role) is not None or role != 'stock'):
                    tex.image = images.get(role)
            else:
                _localize_tree(local, images, tag, copies)
        n.node_tree = local


# ---------------------------------------------------------------- 材质
class TextureSet:
    def __init__(self, md, index, facemap_override=''):
        t = md.textures
        f = index.find
        self.main = f(t.get('_MainTex'))
        self.light = f(t.get('_LightMap'))
        self.warm = f(t.get('_DiffuseRampMultiTex'))
        self.cool = f(t.get('_DiffuseCoolRampMultiTex')) or self.warm
        self.stock = f(t.get('_StockRangeTex'))
        self.facemap = facemap_override if facemap_override and os.path.isfile(facemap_override) else f(t.get('_FaceMap'))
        self.expression = f(t.get('_FaceExpression'))

    def report(self, kind):
        need = {'主贴图': self.main}
        if kind in (KIND_BASE, KIND_HAIR, KIND_WEAPON):
            need.update({'LightMap': self.light, 'Ramp': self.warm})
        if kind == KIND_FACE:
            need['FaceMap'] = self.facemap
        return [k for k, v in need.items() if not v]


def build_material(md, kind, char, tpl, index, opts, uv1_name):
    """根据一份 JSON 生成一个 StellarToon 材质和对应描边材质。"""
    tex = TextureSet(md, index, opts.get('facemap_override', '') if kind == KIND_FACE else '')
    tag = f'{char}:{md.stem}'
    mat_name = f'ST_{char}_{md.stem}'

    src = tpl[TPL_MATERIALS[kind]]
    mat = bpy.data.materials.get(mat_name)
    if mat is None or mat.get(CHAR_TAG) != char:
        mat = src.copy()
        mat.name = mat_name
    mat.use_fake_user = False
    if TPL_TAG in mat:
        del mat[TPL_TAG]
    mat[CHAR_TAG] = char
    mat['stmmd_json'] = md.path
    mat['stmmd_kind'] = kind
    nt = mat.node_tree

    main = _load_image(tex.main, False)
    light = _load_image(tex.light, True)
    if kind == KIND_FACE:
        n = nt.nodes.get('Face_Color')
        if n:
            n.image = main
        n = nt.nodes.get('ExpressionMap')
        if n and tex.expression:
            n.image = _load_image(tex.expression, True)
    else:
        p = TEX_PREFIX[kind]
        for suffix, img in (('_Color_UV0', main), ('_Color_UV1', main),
                            ('_Lightmap_UV0', light), ('_Lightmap_UV1', light)):
            n = nt.nodes.get(p + suffix)
            if n:
                n.image = img

    images = {
        'warm': _load_image(tex.warm, False),
        'cool': _load_image(tex.cool, False),
        'facemap': _load_image(tex.facemap, True),
        'stock': _load_image(tex.stock, True) if tex.stock else None,
    }
    stock_img = images['stock']
    # 主节点组和它里面装贴图的子节点组都按材质复制，否则所有材质共用同一张 Ramp / FaceMap
    main_node = _main_group_node(mat)
    if main_node is None:
        raise BuildError(f'{mat.name}: 找不到 StellarToon 主节点组')
    _localize_tree(nt, images, tag, {})

    n = nt.nodes.get('Body_Stockings')
    if n and stock_img:
        n.image = stock_img

    for n in nt.nodes:
        if n.type == 'UVMAP':
            n.uv_map = uv1_name

    main_node = _main_group_node(mat)
    apply_params(main_node, md, kind)
    if kind in (KIND_BASE, KIND_WEAPON):
        set_input(main_node, 'Enable Stockings', 1.0 if stock_img else 0.0)
    if kind == KIND_FACE:
        set_input(main_node, 'Enable Emission', 1.0)
    elif not opts.get('emission', False):
        set_input(main_node, 'Enable Emission', 0.0)
    else:
        # 开了透明裁切（_EnableAlphaCutoff）的材质，主贴图 alpha 是透明遮罩不是发光遮罩，开发光会整片过曝
        glow = (md.get('_EmissionIntensity') or 0) > 0 and not (md.get('_EnableAlphaCutoff') or 0)
        set_input(main_node, 'Enable Emission', 1.0 if glow else 0.0)

    # 描边材质
    ol_src = tpl[TPL_MATERIALS[kind] + ' Outlines']
    ol_name = mat_name + ' Outlines'
    ol = bpy.data.materials.get(ol_name)
    if ol is None or ol.get(CHAR_TAG) != char:
        ol = ol_src.copy()
        ol.name = ol_name
    ol.use_fake_user = False
    if TPL_TAG in ol:
        del ol[TPL_TAG]
    ol[CHAR_TAG] = char
    ont = ol.node_tree
    n = ont.nodes.get('Image Texture.001')
    if n:
        n.image = main
    n = ont.nodes.get('Image Texture.002')
    if n:
        n.image = light
    ol_node = _main_group_node(ol)
    if ol_node:
        for i in range(8):
            keys = [f'_OutlineColor{i}'] + (['_OutlineColor'] if i == 0 else [])
            for k in keys:
                v = md.colors.get(k)
                if v is not None:
                    set_input(ol_node, f'Outline Color {i + 1}', v)
                    break
    mat['stmmd_outline'] = ol.name
    mat['stmmd_outline_width'] = float(md.get('_OutlineWidth') or 0.045)
    return mat, ol, tex.report(kind)


def material_variant(mat, outline=True, cull=None):
    """同一份参数的变体：不进描边遮罩（眼睛/牙齿等）或双面（MMD 里标了双面的材质）。
    StellarToon 默认单面（背面剔除）：MMD 模型的“xx+”材质是翻转法线的内层，
    不剔除背面的话，外层会被内层的背面（走 UV1 采样）盖住，裙摆一类部位看起来发黑/透明。"""
    if cull is None:
        cull = True
    if outline and cull:
        return mat
    name = mat.name + ('' if outline else ' (无描边)') + ('' if cull else ' (双面)')
    m = bpy.data.materials.get(name)
    if m is None or m.get(CHAR_TAG) != mat.get(CHAR_TAG):
        m = mat.copy()
        m.name = name
    for k in (CHAR_TAG, 'stmmd_json', 'stmmd_kind', 'stmmd_outline', 'stmmd_outline_width'):
        if k in mat:
            m[k] = mat[k]
    m.use_backface_culling = cull
    if not outline:
        m['stmmd_no_outline'] = True
        if 'stmmd_outline' in m:
            del m['stmmd_outline']
    return m


def no_outline_variant(mat):
    return material_variant(mat, outline=False, cull=mat.use_backface_culling)


def _restore_slots(obj):
    orig = json.loads(obj.get(ORIG_TAG, '{}'))
    for i, slot in enumerate(obj.material_slots):
        name = orig.get(str(i))
        if name and bpy.data.materials.get(name):
            slot.material = bpy.data.materials[name]
    if ORIG_TAG in obj:
        del obj[ORIG_TAG]


def split_by_materials(context, arm, meshes):
    """用 mmd_tools 的“按材质分开”把整块网格拆成每个材质一个物体（与手动 StellarToon 工程的做法一致）。
    已经挂过 StellarToon 的网格先还原 MMD 原材质，因为 mmd_tools 拆分时按原材质名排序。"""
    if not hasattr(bpy.ops.mmd_tools, 'separate_by_materials'):
        raise BuildError('需要 mmd_tools 才能按材质拆分（或关闭“按材质拆分”选项）')
    todo = [o for o in meshes if len(o.material_slots) > 1]
    if not todo:
        return meshes, 0
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in todo:
        _restore_slots(obj)
        for m in list(obj.modifiers):
            if m.name.startswith(MOD_LV) or m.name.startswith(MOD_OL):
                obj.modifiers.remove(m)
        if CHAR_TAG in obj:
            del obj[CHAR_TAG]
        for o in context.view_layer.objects:
            o.select_set(False)
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.mmd_tools.separate_by_materials()
    from . import matching
    return matching.model_meshes(arm), len(todo)


# ---------------------------------------------------------------- 几何节点
def _gn_sockets(group, in_out):
    if hasattr(group, 'interface'):
        return [(it.name, it.identifier) for it in group.interface.items_tree
                if getattr(it, 'item_type', 'SOCKET') == 'SOCKET' and it.in_out == in_out]
    socks = group.inputs if in_out == 'INPUT' else group.outputs
    return [(s.name, s.identifier) for s in socks]


def set_gn_inputs(mod, values):
    ids = {}
    for name, ident in _gn_sockets(mod.node_group, 'INPUT'):
        ids.setdefault(name, ident)
    for name, value in values.items():
        ident = ids.get(name)
        if ident is None:
            continue
        try:
            mod[ident] = value
        except (TypeError, ValueError):
            try:
                mod[ident] = float(value)
            except Exception:
                pass


def set_gn_output_attributes(mod):
    for name, ident in _gn_sockets(mod.node_group, 'OUTPUT'):
        if name == 'Geometry' or '**' in name:
            continue
        try:
            mod[ident + '_attribute_name'] = name
        except Exception:
            pass


def _ensure_mod(obj, name, group):
    mod = obj.modifiers.get(name)
    if mod is None or mod.type != 'NODES':
        mod = obj.modifiers.new(name, 'NODES')
    mod.node_group = group
    return mod


# ---------------------------------------------------------------- 空物体（光照 / 头部方向）
HEAD_BONES = ('頭', 'head', 'Head', '头', 'J_Bip_C_Head', 'Bip001 Head')


def find_head_bone(arm):
    for n in HEAD_BONES:
        if n in arm.pose.bones:
            return n
    for pb in arm.pose.bones:
        mb = getattr(pb, 'mmd_bone', None)
        if mb and getattr(mb, 'name_e', '').lower() == 'head':
            return pb.name
    for pb in arm.pose.bones:
        if 'head' in pb.name.lower():
            return pb.name
    return None


def _new_empty(name, coll, display='PLAIN_AXES', size=0.1):
    o = bpy.data.objects.new(name, None)
    o.empty_display_type = display
    o.empty_display_size = size
    coll.objects.link(o)
    return o


def ensure_light(scene, coll, head_world):
    light = scene.get('stmmd_light')
    if isinstance(light, bpy.types.Object) and light.name in bpy.data.objects:
        return light
    for o in bpy.data.objects:
        if o.get('stmmd_light_dir'):
            scene['stmmd_light'] = o
            return o
    o = _new_empty('Main Light Direction', coll, 'SINGLE_ARROW', 0.4)
    o['stmmd_light_dir'] = True
    o.location = head_world + Vector((0.6, -0.8, 0.4))
    o.rotation_euler = (-1.92, 0.0, 0.0)  # 与 StellarToon 模板默认值一致：正面偏上的主光
    scene['stmmd_light'] = o
    return o


FOLLOW_CON = 'STMMD 跟随灯光'


def link_light(scene, target):
    """让 Main Light Direction 跟着场景里的灯/物体转。
    StellarToon 把空物体旋转后的 (0,0,-1) 当作“指向光源”的方向；
    Blender 的日光/聚光/面光沿自身 -Z 照射，指向光源的方向是 +Z，所以要额外绕本地 X 转 180°。"""
    light = ensure_light(scene, scene.collection, Vector((0, 0, 1.5)))
    for c in list(light.constraints):
        if c.name.startswith(FOLLOW_CON):
            light.constraints.remove(c)
    if target is None:
        return light, None
    if target == light:
        raise BuildError('不能让 Main Light Direction 跟随它自己')
    directional = target.type == 'LIGHT' and target.data.type in {'SUN', 'SPOT', 'AREA'}
    if directional:
        light.rotation_euler = (math.pi, 0.0, 0.0)
        con = light.constraints.new('COPY_ROTATION')
        con.target = target
        con.mix_mode = 'BEFORE'          # 结果 = 灯的世界旋转 × 本地 180°
        con.target_space = 'WORLD'
        con.owner_space = 'WORLD'
        mode = '方向'
    else:
        # 点光源或普通物体（比如天空里的太阳模型）：让 -Z 指向它的位置
        light.rotation_euler = (0.0, 0.0, 0.0)
        con = light.constraints.new('DAMPED_TRACK')
        con.target = target
        con.track_axis = 'TRACK_NEGATIVE_Z'
        mode = '位置'
    con.name = FOLLOW_CON
    light['stmmd_follow'] = target.name
    return light, mode


def linked_light(scene):
    light = scene.get('stmmd_light')
    if not isinstance(light, bpy.types.Object):
        return None
    for c in light.constraints:
        if c.name.startswith(FOLLOW_CON) and c.target:
            return c.target
    return None


def ensure_rig(context, arm, char):
    scene = context.scene
    coll_name = f'StellarToon - {char}'
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        coll = bpy.data.collections.new(coll_name)
        scene.collection.children.link(coll)
    coll[CHAR_TAG] = char

    bone = find_head_bone(arm)
    if bone is None:
        raise BuildError('找不到头部骨骼（頭 / head），无法放置头部方向空物体')
    pb = arm.pose.bones[bone]
    head_mat = arm.matrix_world @ pb.matrix
    head_world = head_mat.translation.copy()
    rot = arm.matrix_world.to_3x3().normalized()
    fwd = (rot @ Vector((0, -1, 0))).normalized() * 0.78   # MMD 模型面朝 -Y
    up = (rot @ Vector((0, 0, 1))).normalized() * 0.54

    def get_or_new(key, name, display, size):
        for o in coll.objects:
            if o.get('stmmd_role') == key:
                return o
        o = _new_empty(f'{name} - {char}', coll, display, size)
        o['stmmd_role'] = key
        o[CHAR_TAG] = char
        return o

    origin = get_or_new('origin', 'Head Origin', 'SPHERE', 0.05)
    origin.parent = None
    origin.matrix_world = Matrix.Translation(head_world)
    con = origin.constraints.get('STMMD Head') or origin.constraints.new('CHILD_OF')
    con.name = 'STMMD Head'
    con.target = arm
    con.subtarget = bone
    con.inverse_matrix = head_mat.inverted()

    forward = get_or_new('forward', 'Head Forward', 'SINGLE_ARROW', 0.1)
    upo = get_or_new('up', 'Head Up', 'SINGLE_ARROW', 0.1)
    for o, off in ((forward, fwd), (upo, up)):
        o.parent = origin
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.location = off
        o.rotation_euler = (0, 0, 0)

    light = ensure_light(scene, coll, head_world)
    return {'origin': origin, 'forward': forward, 'up': upo, 'light': light, 'collection': coll,
            'head_bone': bone}


# ---------------------------------------------------------------- 主流程
# 描边 GN 内部：偏移 = 法线 × Outline Thickness × 0.01 × 0.08（不用顶点色时）× 距离倍率（屏幕空间时）
_GN_FACTOR = 0.01 * 0.08
# 游戏 _OutlineWidth 典型值 0.045 时：世界空间约为模型身高的 0.12%，屏幕空间约为相机距离的 0.06%
_WORLD_RATIO = 0.0012
_SCREEN_RATIO = 0.0006


def model_height(meshes):
    zs = []
    for o in meshes:
        for c in o.bound_box:
            zs.append((o.matrix_world @ Vector(c)).z)
    return (max(zs) - min(zs)) if zs else 1.6


def outline_thickness(width, opts, height):
    k = (width / 0.045) * opts.get('outline_scale', 1.0)
    if opts.get('screen_space'):
        return k * _SCREEN_RATIO / _GN_FACTOR
    return k * _WORLD_RATIO * height / _GN_FACTOR


def setup_outline_modifier(obj, tpl, opts, camera, height=1.6):
    """按网格上的 StellarToon 材质设置描边几何节点；每个修改器最多 5 组遮罩，超出时追加修改器。"""
    for m in list(obj.modifiers):
        if m.name.startswith(MOD_OL):
            obj.modifiers.remove(m)
    mats = []
    for slot in obj.material_slots:
        m = slot.material
        if m and m.get(CHAR_TAG) and m.get('stmmd_outline') and m not in mats:
            mats.append(m)
    if not mats or not opts.get('outline', True):
        return 0
    widths = [float(m.get('stmmd_outline_width', 0.045)) for m in mats]
    screen = bool(opts.get('screen_space') and camera)
    thickness = outline_thickness(sum(widths) / len(widths), dict(opts, screen_space=screen), height)
    if any(m.get('stmmd_kind') == KIND_FACE for m in mats):
        thickness *= opts.get('face_outline_scale', 1.0)
    count = 0
    for start in range(0, len(mats), 5):
        chunk = mats[start:start + 5]
        name = MOD_OL if start == 0 else f'{MOD_OL} {start // 5 + 1}'
        mod = obj.modifiers.new(name, 'NODES')
        mod.node_group = tpl[GN_OUTLINE]
        values = {
            'Rotate Normals **UNUSED**': 0,
            'Use Base Geometry?': 1,
            'Use Vertex Colors?': 0,
            'Screen Space Switch': 1.0 if screen else 0.0,
            'Outline Thickness': thickness,
            'Clamp Minimum Distance Mult?': False,
            'Clamp Maximum Distance Mult?': True,
            'Maximum Distance Mult': 20.0 * height,
        }
        if camera:
            values['Camera'] = camera
        for i in range(5):
            if i < len(chunk):
                values[f'Outline {i + 1} Mask'] = chunk[i]
                values[f'Outline {i + 1} Material'] = bpy.data.materials.get(chunk[i]['stmmd_outline'])
            else:
                values[f'Outline {i + 1} Mask'] = None
                values[f'Outline {i + 1} Material'] = None
        set_gn_inputs(mod, values)
        count += 1
    return count


def apply_to_model(context, arm, meshes, assignments, materials_data, index, char, template_path, opts):
    """
    assignments: {原 MMD 材质名: (json_stem 或 '', 是否描边)}
    materials_data: {json_stem: (MaterialData, kind)}
    """
    tpl = load_template(template_path)
    uv1 = ''
    if opts.get('use_uv1', True) and meshes and all('UV1' in o.data.uv_layers for o in meshes):
        uv1 = 'UV1'

    built = {}
    warnings = []
    for orig_name, (stem, _outline) in assignments.items():
        if not stem or stem in built:
            continue
        md, kind = materials_data[stem]
        mat, _ol, miss = build_material(md, kind, char, tpl, index, opts, uv1)
        mat.use_backface_culling = True   # 与 MMD 一致的单面；双面材质走 material_variant
        built[stem] = mat
        if miss:
            warnings.append(f'{md.stem} 缺贴图: ' + '、'.join(miss))

    rig = ensure_rig(context, arm, char)
    camera = context.scene.camera
    height = model_height(meshes)

    changed = 0
    for obj in meshes:
        orig = json.loads(obj.get(ORIG_TAG, '{}'))
        touched = False
        for i, slot in enumerate(obj.material_slots):
            m = slot.material
            if m is None:
                continue
            src_name = orig.get(str(i), m.name) if m.get(CHAR_TAG) else m.name
            stem, outline = assignments.get(src_name, ('', True))
            if not stem:
                if m.get(CHAR_TAG) and str(i) in orig:  # 之前挂过、这次改成跳过 → 还原
                    restored = bpy.data.materials.get(orig.pop(str(i)))
                    if restored:
                        slot.material = restored
                continue
            src_mat = bpy.data.materials.get(src_name)
            cull = src_mat.use_backface_culling if src_mat is not None else True
            target = material_variant(built[stem], outline, cull)
            orig.setdefault(str(i), src_name)
            slot.material = target
            touched = True
            changed += 1
        if orig:
            obj[ORIG_TAG] = json.dumps(orig, ensure_ascii=False)
        if not touched:
            for mname in (MOD_LV,):
                if obj.modifiers.get(mname):
                    obj.modifiers.remove(obj.modifiers[mname])
            setup_outline_modifier(obj, tpl, {'outline': False}, camera)
            continue
        lv = _ensure_mod(obj, MOD_LV, tpl[GN_LIGHT])
        set_gn_inputs(lv, {'Light Direction': rig['light'], 'Head Origin': rig['origin'],
                           'Head Forward': rig['forward'], 'Head Up': rig['up']})
        set_gn_output_attributes(lv)
        setup_outline_modifier(obj, tpl, opts, camera, height)
        obj[CHAR_TAG] = char

    arm[CHAR_TAG] = char
    if opts.get('scene_settings', True):
        vs = context.scene.view_settings
        try:
            vs.view_transform = 'Standard'
            vs.look = 'None'
        except TypeError:
            pass
        set_goo_render(context.scene)
        ee = context.scene.eevee
        if hasattr(ee, 'use_bloom'):
            ee.use_bloom = True
            ee.bloom_threshold = 0.8
            ee.bloom_intensity = 0.05
    return changed, len(built), warnings


def is_goo_build():
    return 'goo' in (bpy.app.version_string + str(getattr(bpy.app, 'build_branch', b''))).lower()


def goo_render_problems(scene):
    """StellarToon 的脸部依赖 Goo 渲染器（旧版 EEVEE）的屏幕空间反射 + 折射，缺一个脸就会发黑。"""
    probs = []
    if scene.render.engine != 'BLENDER_EEVEE':
        probs.append('渲染引擎不是 Goo Engine')
    ee = scene.eevee
    if not getattr(ee, 'use_ssr', False):
        probs.append('未开启屏幕空间反射')
    if not getattr(ee, 'use_ssr_refraction', False):
        probs.append('未开启屏幕空间反射里的“折射”')
    return probs


def set_goo_render(scene):
    if is_goo_build():
        try:
            # Goo 4.x 里 'BLENDER_EEVEE' 就是界面上的“Goo Engine”（旧版 EEVEE），不是 EEVEE Next
            scene.render.engine = 'BLENDER_EEVEE'
        except TypeError:
            pass
    ee = scene.eevee
    if hasattr(ee, 'use_ssr'):
        ee.use_ssr = True
        ee.use_ssr_refraction = True


def update_outlines(context, arm, meshes, template_path, opts):
    tpl = load_template(template_path)
    height = model_height(meshes)
    n = 0
    for obj in meshes:
        if obj.get(CHAR_TAG):
            n += setup_outline_modifier(obj, tpl, opts, context.scene.camera, height)
    return n


def revert_model(context, arm, meshes):
    char = arm.get(CHAR_TAG)
    restored = 0
    for obj in meshes:
        orig = json.loads(obj.get(ORIG_TAG, '{}'))
        for i, slot in enumerate(obj.material_slots):
            name = orig.get(str(i))
            if name and bpy.data.materials.get(name):
                slot.material = bpy.data.materials[name]
                restored += 1
        for m in list(obj.modifiers):
            if m.name.startswith(MOD_LV) or m.name.startswith(MOD_OL):
                obj.modifiers.remove(m)
        for k in (ORIG_TAG, CHAR_TAG):
            if k in obj:
                del obj[k]
    if char:
        coll = bpy.data.collections.get(f'StellarToon - {char}')
        if coll:
            for o in list(coll.objects):
                if o.get('stmmd_light_dir'):
                    # 主光可能被其他角色共用，移到场景根集合保留
                    still_used = any(ob.get(CHAR_TAG) and ob.get(CHAR_TAG) != char for ob in bpy.data.objects
                                     if ob.type == 'MESH')
                    if still_used:
                        context.scene.collection.objects.link(o)
                        coll.objects.unlink(o)
                        continue
                bpy.data.objects.remove(o)
            bpy.data.collections.remove(coll)
        for coll in (bpy.data.materials, bpy.data.node_groups):
            for d in list(coll):
                if d.get(CHAR_TAG) == char and d.users == 0:
                    coll.remove(d)
        del arm[CHAR_TAG]
    return restored
