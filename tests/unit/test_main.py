"""Unit tests for dcmspec_explorer.main."""

from dcmspec_explorer.main import apply_style


class FakeApp:
    """Records the style names passed to setStyle."""

    def __init__(self):
        """Initialize with no recorded styles."""
        self.styles = []

    def setStyle(self, name):
        """Record the requested style name."""
        self.styles.append(name)


class TestApplyStyle:
    """Tests for apply_style."""

    def test_sets_fusion_by_default(self, monkeypatch):
        """With no QT_STYLE_OVERRIDE, the Fusion style is set."""
        monkeypatch.delenv("QT_STYLE_OVERRIDE", raising=False)
        app = FakeApp()

        apply_style(app)

        assert app.styles == ["Fusion"]

    def test_sets_fusion_when_override_is_empty(self, monkeypatch):
        """An empty QT_STYLE_OVERRIDE selects no style, so the Fusion style is set."""
        monkeypatch.setenv("QT_STYLE_OVERRIDE", "")
        app = FakeApp()

        apply_style(app)

        assert app.styles == ["Fusion"]

    def test_keeps_style_override(self, monkeypatch):
        """A style chosen through QT_STYLE_OVERRIDE is left alone."""
        monkeypatch.setenv("QT_STYLE_OVERRIDE", "macos")
        app = FakeApp()

        apply_style(app)

        assert app.styles == []
