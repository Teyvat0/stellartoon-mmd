# 操作符与界面
import os

import bpy
from bpy.props import (BoolProperty, CollectionProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)

from . import builder, matching
from .json_data import KIND_FACE, KIND_LABELS, TextureIndex, scan_materials

ADDON_ID = __package__

# 扫描结果缓存：{角色目录: (MaterialData 列表, TextureIndex)}
_cache = {}


def prefs(context=None):
    context = context or bpy.context
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def load_character(char_dir, facemap_dir, refresh=False):
    key = (os.path.normcase(os.path.normpath(char_dir)), facemap_dir or '')
    if refresh or key not in _cache:
        mats = scan_materials(char_dir)
        index = TextureIndex()
        index.add_dir(char_dir)
        # 角色目录里没有的贴图（如通用 FaceMap）去上一级、面部阴影目录里找
        if facemap_dir:
            index.add_dir(facemap_dir)
        _cache[key] = (mats, index)
    return _cache[key]


def active_armature(context):
    return matching.find_armature(context.active_object)


# ---------------------------------------------------------------- 数据
class STMMD_JsonItem(bpy.types.PropertyGroup):
    # name = JSON 文件名（不含扩展名）
    path: StringProperty()
    kind: StringProperty()
    label: StringProperty()


class STMMD_MatItem(bpy.types.PropertyGroup):
    # name = MMD 原材质名
    display: StringProperty()
    target: StringProperty(name='游戏材质', description='留空表示保持 MMD 原材质')
    outline: BoolProperty(name='描边', default=True)
    score: FloatProperty(default=-1.0)


def _guess_char_name(path):
    p = os.path.normpath(path)
    base = os.path.basename(p)
    if base.lower() in ('materials', 'textures'):
        p = os.path.dirname(p)
        base = os.path.basename(p)
    if base.lower() in ('default', 'skin', 'base', '00'):
        base = os.path.basename(os.path.dirname(p))
    return base.replace(' ', '')


def _on_char_dir(self, _context):
    if self.char_dir and not self.char_name:
        self.char_name = _guess_char_name(bpy.path.abspath(self.char_dir))


def _light_target_poll(self, obj):
    return not obj.get('stmmd_light_dir') and obj.type in {'LIGHT', 'EMPTY', 'MESH'}


class STMMD_Settings(bpy.types.PropertyGroup):
    char_dir: StringProperty(name='角色资源目录', subtype='DIR_PATH', update=_on_char_dir,
                             description='HoyoToon-Assets 里的角色文件夹（包含 Materials 和 Textures）')
    char_name: StringProperty(name='角色名', description='生成的材质、空物体用这个名字区分')
    facemap_override: StringProperty(name='指定面部阴影图', subtype='FILE_PATH',
                                     description='留空则按脸部 JSON 里的 _FaceMap 名字自动找')
    outline: BoolProperty(name='描边', default=True)
    screen_space: BoolProperty(name='屏幕空间描边', default=False,
                               description='描边粗细随相机距离保持一致（需要场景相机）')
    outline_scale: FloatProperty(name='描边倍率', default=1.0, min=0.0, soft_max=5.0)
    face_outline_scale: FloatProperty(name='脸部描边倍率', default=1.0, min=0.0, soft_max=5.0,
                                      description='只乘到脸/眉/嘴的描边上。游戏里脸部描边本来就细，且粗细靠顶点色控制，MMD 模型没有这份顶点色')
    light_target: PointerProperty(name='跟随灯光', type=bpy.types.Object, poll=_light_target_poll,
                                  description='日光/聚光/面光按方向跟随；点光或普通物体（如天空里的太阳模型）按位置跟随')
    emission: BoolProperty(name='自发光', default=False,
                           description='按 JSON 的 _EmissionIntensity 开启身体/头发自发光。部分角色（如爻光）主贴图 alpha 不是发光遮罩，开了会过曝')
    split: BoolProperty(name='按材质拆分', default=True,
                        description='应用前用 mmd_tools 的“按材质分开”把网格拆成每个材质一个物体，便于之后单独调试')
    scene_settings: BoolProperty(name='调整场景色彩', default=True,
                                 description='色彩管理改为 Standard，EEVEE 旧版开启弱辉光')
    use_uv1: BoolProperty(name='背面用 UV1', default=True,
                          description='模板对背面（如裙子内侧）改用第二套 UV 采样贴图；MMD 模型的 UV1 不是游戏 UV1 时关掉')
    jsons: CollectionProperty(type=STMMD_JsonItem)
    items: CollectionProperty(type=STMMD_MatItem)
    items_index: IntProperty()
    armature: StringProperty()


# ---------------------------------------------------------------- 偏好设置
class STMMD_Prefs(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    template_path: StringProperty(
        name='StellarToon 模板 .blend', subtype='FILE_PATH',
        description='自行准备的 StellarToon 工程（例如 StellarToon-MMD-fix.blend），插件只从中追加材质和节点组')
    facemap_dir: StringProperty(
        name='面部阴影贴图目录', subtype='DIR_PATH',
        description='存放 W_170_Lady_FaceMap_00.png 等通用面部 SDF 贴图的文件夹')

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, 'template_path')
        ok, missing = builder.template_status(bpy.path.abspath(self.template_path)) if self.template_path else (False, ['未设置'])
        row = col.row()
        row.label(text='模板可用' if ok else '模板不可用: ' + '，'.join(missing[:4]),
                  icon='CHECKMARK' if ok else 'ERROR')
        col.prop(self, 'facemap_dir')
        col.label(text='插件不附带任何模板或游戏资源，请使用你自己有权使用的文件。', icon='INFO')


# ---------------------------------------------------------------- 操作符
class STMMD_OT_scan(bpy.types.Operator):
    bl_idname = 'stmmd.scan'
    bl_label = '读取并自动匹配'
    bl_description = '读取角色目录里的材质 JSON，并按贴图内容匹配模型的每个材质'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        st = context.scene.stmmd
        p = prefs(context)
        arm = active_armature(context)
        if arm is None:
            self.report({'ERROR'}, '请先选中 MMD 模型（骨架或网格）')
            return {'CANCELLED'}
        char_dir = bpy.path.abspath(st.char_dir)
        if not os.path.isdir(char_dir):
            self.report({'ERROR'}, '角色资源目录不存在')
            return {'CANCELLED'}
        mats, index = load_character(char_dir, bpy.path.abspath(p.facemap_dir) if p else '', refresh=True)
        if not mats:
            self.report({'ERROR'}, '目录里没有可用的角色材质 JSON')
            return {'CANCELLED'}
        if not st.char_name:
            st.char_name = _guess_char_name(char_dir)
        st.armature = arm.name

        st.jsons.clear()
        for md in mats:
            it = st.jsons.add()
            it.name = md.stem
            it.path = md.path
            it.kind = md.kind
            it.label = KIND_LABELS.get(md.kind, md.kind)

        # 每个游戏主贴图只比较一次；同一主贴图的 D/S 两份优先 D（双面）
        by_tex = {}
        for md in mats:
            tp = index.find(md.main_tex)
            if not tp:
                continue
            cur = by_tex.get(tp)
            if cur is None or (cur.variant != 'D' and md.variant == 'D'):
                by_tex[tp] = md

        meshes = matching.model_meshes(arm)
        st.items.clear()
        matched = 0
        unsure = 0
        for m in matching.collect_materials(meshes):
            it = st.items.add()
            it.name = m.name
            it.display = matching.mmd_display_name(m)
            it.outline = matching.wants_outline(m)
            src = matching.base_texture_path(m)
            best, best_d, sure = matching.pick_match(src, list(by_tex.items())) if src else (None, None, False)
            if best is not None:
                it.target = best.stem
                it.score = best_d
                matched += 1
                if not sure:
                    unsure += 1
            else:
                it.target = ''
                it.score = best_d if best_d is not None else -1.0
        msg = f'{len(st.items)} 个材质，自动匹配 {matched} 个'
        if unsure:
            msg += f'（其中 {unsure} 个贴图被 MMD 作者改过，按“最像”匹配）'
        self.report({'INFO'}, msg + '；请检查列表后点“应用”')
        return {'FINISHED'}


class STMMD_OT_apply(bpy.types.Operator):
    bl_idname = 'stmmd.apply'
    bl_label = '应用 StellarToon'
    bl_description = '按列表生成 StellarToon 材质，挂上光照方向与描边几何节点'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        st = context.scene.stmmd
        p = prefs(context)
        tpl = bpy.path.abspath(p.template_path) if p else ''
        arm = bpy.data.objects.get(st.armature) or active_armature(context)
        if arm is None:
            self.report({'ERROR'}, '找不到模型骨架，请先点“读取并自动匹配”')
            return {'CANCELLED'}
        if not st.items:
            self.report({'ERROR'}, '材质列表为空，请先点“读取并自动匹配”')
            return {'CANCELLED'}
        char_dir = bpy.path.abspath(st.char_dir)
        mats, index = load_character(char_dir, bpy.path.abspath(p.facemap_dir) if p else '')
        by_stem = {md.stem: md for md in mats}
        assignments = {}
        data = {}
        for it in st.items:
            stem = it.target.strip()
            if stem and stem not in by_stem:
                self.report({'ERROR'}, f'{it.display}: 找不到游戏材质 {stem}')
                return {'CANCELLED'}
            assignments[it.name] = (stem, it.outline)
            if stem:
                data[stem] = (by_stem[stem], by_stem[stem].kind)
        if not data:
            self.report({'ERROR'}, '没有任何材质指定了游戏材质')
            return {'CANCELLED'}
        opts = {
            'outline': st.outline,
            'screen_space': st.screen_space,
            'outline_scale': st.outline_scale,
            'face_outline_scale': st.face_outline_scale,
            'emission': st.emission,
            'scene_settings': st.scene_settings,
            'use_uv1': st.use_uv1,
            'facemap_override': bpy.path.abspath(st.facemap_override) if st.facemap_override else '',
        }
        if st.screen_space and context.scene.camera is None:
            self.report({'WARNING'}, '场景没有相机，屏幕空间描边已改为世界空间')
        char = (st.char_name or arm.name).strip()
        meshes = matching.model_meshes(arm)
        try:
            if st.split:
                meshes, n_split = builder.split_by_materials(context, arm, meshes)
                if n_split:
                    self.report({'INFO'}, f'已按材质拆分为 {len(meshes)} 个物体')
            changed, built, warnings = builder.apply_to_model(
                context, arm, meshes, assignments, data, index, char, tpl, opts)
        except builder.BuildError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        for w in warnings:
            self.report({'WARNING'}, w)
        builder.set_goo_render(context.scene)
        if st.light_target:
            try:
                builder.link_light(context.scene, st.light_target)
            except builder.BuildError as e:
                self.report({'WARNING'}, str(e))
        if not builder.is_goo_build():
            self.report({'WARNING'}, 'StellarToon 依赖 Goo Engine 专有节点，普通 Blender 下效果不完整')
        self.report({'INFO'}, f'生成 {built} 个材质，替换 {changed} 个材质槽')
        return {'FINISHED'}


class STMMD_OT_update_outlines(bpy.types.Operator):
    bl_idname = 'stmmd.update_outlines'
    bl_label = '刷新描边'
    bl_description = '只按当前描边选项重建描边修改器'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        st = context.scene.stmmd
        p = prefs(context)
        arm = bpy.data.objects.get(st.armature) or active_armature(context)
        if arm is None:
            return {'CANCELLED'}
        opts = {'outline': st.outline, 'screen_space': st.screen_space, 'outline_scale': st.outline_scale,
                'face_outline_scale': st.face_outline_scale}
        try:
            n = builder.update_outlines(context, arm, matching.model_meshes(arm),
                                        bpy.path.abspath(p.template_path), opts)
        except builder.BuildError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, f'描边修改器 {n} 个')
        return {'FINISHED'}


class STMMD_OT_revert(bpy.types.Operator):
    bl_idname = 'stmmd.revert'
    bl_label = '还原 MMD 材质'
    bl_description = '换回原材质，删除本插件添加的修改器、空物体和无人使用的材质'
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        st = context.scene.stmmd
        arm = bpy.data.objects.get(st.armature) or active_armature(context)
        if arm is None:
            return {'CANCELLED'}
        n = builder.revert_model(context, arm, matching.model_meshes(arm))
        self.report({'INFO'}, f'还原 {n} 个材质槽')
        return {'FINISHED'}


class STMMD_OT_select_light(bpy.types.Operator):
    bl_idname = 'stmmd.select_light'
    bl_label = '选中主光方向'
    bl_description = '选中 Main Light Direction 空物体，旋转它即可改变光照方向'

    def execute(self, context):
        light = context.scene.get('stmmd_light')
        if not isinstance(light, bpy.types.Object) or light.name not in context.view_layer.objects:
            self.report({'ERROR'}, '还没有创建主光方向，先应用一次')
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        light.select_set(True)
        context.view_layer.objects.active = light
        return {'FINISHED'}


class STMMD_OT_link_light(bpy.types.Operator):
    bl_idname = 'stmmd.link_light'
    bl_label = '绑定到灯光'
    bl_description = '给 Main Light Direction 加约束，让人物打光跟着所选灯光（或物体）走'
    bl_options = {'REGISTER', 'UNDO'}
    unlink: BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        st = context.scene.stmmd
        target = None if self.unlink else st.light_target
        if not self.unlink and target is None:
            self.report({'ERROR'}, '先在“跟随灯光”里选一个灯或物体')
            return {'CANCELLED'}
        try:
            light, mode = builder.link_light(context.scene, target)
        except builder.BuildError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        if self.unlink:
            st.light_target = None
            self.report({'INFO'}, '已解除，Main Light Direction 恢复手动旋转')
        else:
            self.report({'INFO'}, f'Main Light Direction 已按{mode}跟随 {target.name}')
        return {'FINISHED'}


# ---------------------------------------------------------------- 界面
class STMMD_UL_items(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        st = context.scene.stmmd
        row = layout.row(align=True)
        mat = bpy.data.materials.get(item.name)
        row.label(text=item.display, icon_value=layout.icon(mat) if mat else 0)
        sub = row.row(align=True)
        sub.alert = not item.target
        sub.prop_search(item, 'target', st, 'jsons', text='')
        row.prop(item, 'outline', text='', icon='MOD_SOLIDIFY')


class STMMD_OT_fix_render(bpy.types.Operator):
    bl_idname = 'stmmd.fix_render'
    bl_label = '修正渲染设置'
    bl_description = '渲染引擎切到 Goo Engine，并开启屏幕空间反射与折射（StellarToon 脸部需要）'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        builder.set_goo_render(context.scene)
        probs = builder.goo_render_problems(context.scene)
        if probs:
            self.report({'WARNING'}, '；'.join(probs))
        return {'FINISHED'}


class STMMD_PT_main(bpy.types.Panel):
    bl_label = 'StellarToon MMD'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'StellarToon'

    def draw(self, context):
        layout = self.layout
        st = context.scene.stmmd
        p = prefs(context)
        if p is None or not p.template_path:
            box = layout.box()
            box.label(text='先在插件偏好设置里选择模板 .blend', icon='ERROR')
            box.operator('preferences.addon_show', text='打开偏好设置').module = ADDON_ID
        arm = active_armature(context)
        probs = builder.goo_render_problems(context.scene)
        if probs:
            box = layout.box()
            box.label(text='渲染设置不对，脸会发黑：', icon='ERROR')
            for t in probs:
                box.label(text='· ' + t)
            box.operator('stmmd.fix_render', icon='CHECKMARK')
        layout.label(text=f'模型: {arm.name}' if arm else '未选中 MMD 模型', icon='ARMATURE_DATA')
        col = layout.column(align=True)
        col.prop(st, 'char_dir', text='')
        col.prop(st, 'char_name')
        layout.operator('stmmd.scan', icon='VIEWZOOM')

        if st.items:
            layout.template_list('STMMD_UL_items', '', st, 'items', st, 'items_index', rows=8)
            if 0 <= st.items_index < len(st.items):
                it = st.items[st.items_index]
                info = layout.row()
                j = st.jsons.get(it.target)
                score = f'贴图差异 {it.score:.3f}' if it.score >= 0 else '无法比较贴图'
                info.label(text=f'{KIND_LABELS.get(j.kind, "") if j else "不替换"} · {score}')

        box = layout.box()
        box.label(text='选项')
        col = box.column(align=True)
        col.prop(st, 'facemap_override')
        row = col.row(align=True)
        row.prop(st, 'outline')
        row.prop(st, 'screen_space')
        col.prop(st, 'outline_scale')
        col.prop(st, 'face_outline_scale')
        row = col.row(align=True)
        row.prop(st, 'emission')
        row.prop(st, 'scene_settings')
        col.prop(st, 'use_uv1')
        col.prop(st, 'split')

        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator('stmmd.apply', icon='SHADING_RENDERED')
        row = layout.row(align=True)
        row.operator('stmmd.update_outlines', icon='MOD_SOLIDIFY')
        row.operator('stmmd.select_light', icon='LIGHT_SUN')
        box = layout.box()
        box.label(text='主光方向', icon='LIGHT_SUN')
        row = box.row(align=True)
        row.prop(st, 'light_target', text='')
        row.operator('stmmd.link_light', text='', icon='LINKED')
        row.operator('stmmd.link_light', text='', icon='UNLINKED').unlink = True
        cur = builder.linked_light(context.scene)
        box.label(text=f'当前跟随: {cur.name}' if cur else '当前: 手动旋转 Main Light Direction')
        layout.operator('stmmd.revert', icon='LOOP_BACK')


classes = (
    STMMD_JsonItem, STMMD_MatItem, STMMD_Settings, STMMD_Prefs,
    STMMD_OT_scan, STMMD_OT_apply, STMMD_OT_update_outlines, STMMD_OT_revert, STMMD_OT_select_light,
    STMMD_OT_fix_render, STMMD_OT_link_light,
    STMMD_UL_items, STMMD_PT_main,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.stmmd = PointerProperty(type=STMMD_Settings)


def unregister():
    del bpy.types.Scene.stmmd
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
