from j2py.config.loader import TranslationConfig
from j2py.translate.class_methods import render_parameter_list
from j2py.translate.class_model import ParameterInfo
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics


def test_render_parameter_list_keeps_spread_prefix_and_registers_param() -> None:
    cfg = TranslationConfig()
    diagnostics = TranslationDiagnostics()
    ctx = TranslationContext(cfg=cfg, diagnostics=diagnostics)
    params = [ParameterInfo("values", "values", "str", "String", is_spread=True)]

    rendered = render_parameter_list(
        params,
        cfg=cfg,
        diagnostics=diagnostics,
        ctx=ctx,
        register=True,
        render_spread=True,
    )

    assert rendered == ["*values: str"]
    assert ctx.param_names == {"values"}
    assert ctx.spread_param_names == {"values"}
    assert ctx.variable_types == {"values": "list[str]"}
    assert ctx.variable_java_types == {"values": "String"}


def test_render_parameter_list_skips_existing_extra_params() -> None:
    cfg = TranslationConfig()
    diagnostics = TranslationDiagnostics()
    ctx = TranslationContext(cfg=cfg, diagnostics=diagnostics)
    ctx.param_names.add("value")
    params = [
        ParameterInfo("value", "value", "str", "String"),
        ParameterInfo("service", "service", "OrderService", "OrderService"),
    ]

    rendered = render_parameter_list(
        params,
        cfg=cfg,
        diagnostics=diagnostics,
        ctx=ctx,
        register=True,
        skip_existing=True,
    )

    assert rendered == ["service: OrderService"]
    assert ctx.param_names == {"value", "service"}
    assert ctx.variable_types == {"service": "OrderService"}
