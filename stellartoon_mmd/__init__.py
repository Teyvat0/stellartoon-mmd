bl_info = {
    'name': 'StellarToon MMD',
    'author': 'Teyvat0',
    'version': (0, 1, 0),
    'blender': (3, 6, 0),
    'location': '3D 视图 > 侧栏 > StellarToon',
    'description': '用游戏材质 JSON 给 MMD 模型挂上 StellarToon（星穹铁道风格）渲染。需要 Goo Engine 和用户自备的模板。',
    'doc_url': 'https://github.com/Teyvat0/stellartoon-mmd',
    'tracker_url': 'https://github.com/Teyvat0/stellartoon-mmd/issues',
    'category': 'Material',
}

if 'ops' in locals():
    import importlib
    from . import json_data, matching, builder, ops  # noqa: F811
    for _m in (json_data, matching, builder, ops):
        importlib.reload(_m)
else:
    from . import ops


def register():
    ops.register()


def unregister():
    ops.unregister()
