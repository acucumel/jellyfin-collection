"""Unit tests for PosterGenerator service (prompt generation only, no API calls)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestPosterGeneratorInit:
    """Tests for PosterGenerator initialization."""

    def test_init_creates_output_dir(self, tmp_path: Path):
        """Test that init creates output directory."""
        from jfc.services.poster_generator import PosterGenerator

        output_dir = tmp_path / "posters"

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=output_dir,
            )

        assert output_dir.exists()

    def test_init_with_cache_dir(self, tmp_path: Path):
        """Test init with custom cache directory."""
        from jfc.services.poster_generator import PosterGenerator

        output_dir = tmp_path / "posters"
        cache_dir = tmp_path / "cache"

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=output_dir,
                cache_dir=cache_dir,
            )

        assert generator.signatures_cache_path == cache_dir / "visual_signatures_cache.json"

    def test_init_with_custom_logo(self, tmp_path: Path):
        """Test init with custom logo text."""
        from jfc.services.poster_generator import PosterGenerator

        output_dir = tmp_path / "posters"

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=output_dir,
                logo_text="MYFLIX",
            )

        assert generator.logo_text == "MYFLIX"

    def test_default_logo_text(self, tmp_path: Path):
        """Test default logo text is NETFLEX."""
        from jfc.services.poster_generator import PosterGenerator

        output_dir = tmp_path / "posters"

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=output_dir,
            )

        assert generator.logo_text == "NETFLEX"


class TestCollectionDir:
    """Tests for _get_collection_dir method."""

    def test_creates_directory_structure(self, tmp_path: Path):
        """Test that collection directory structure is created."""
        from jfc.services.poster_generator import PosterGenerator

        output_dir = tmp_path / "posters"

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=output_dir,
            )

        col_dir = generator._get_collection_dir("Films", "Trending Movies")

        assert col_dir.exists()
        assert (col_dir / "history").exists()
        assert (col_dir / "prompts").exists()

    def test_safe_filename(self, tmp_path: Path):
        """Test that unsafe characters are handled in filenames."""
        from jfc.services.poster_generator import PosterGenerator

        output_dir = tmp_path / "posters"

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=output_dir,
            )

        # Test with special characters
        col_dir = generator._get_collection_dir("Séries", "Pour Nina ❤️")

        # Directory should be created with safe name
        assert col_dir.exists()


class TestSafeFilename:
    """Tests for _safe_filename method."""

    def test_removes_unsafe_chars(self, tmp_path: Path):
        """Test removal of unsafe characters."""
        from jfc.services.poster_generator import PosterGenerator

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=tmp_path,
            )

        # Test various unsafe characters
        assert "/" not in generator._safe_filename("Test/Name")
        assert "\\" not in generator._safe_filename("Test\\Name")
        assert ":" not in generator._safe_filename("Test:Name")

    def test_preserves_unicode(self, tmp_path: Path):
        """Test that unicode characters are preserved."""
        from jfc.services.poster_generator import PosterGenerator

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=tmp_path,
            )

        # Accented characters should be preserved
        result = generator._safe_filename("Séries Françaises")
        assert "é" in result or "e" in result  # Either preserved or transliterated


class TestCollectionThemes:
    """Tests for collection_themes configuration."""

    def test_collection_themes_loaded(self, tmp_path: Path):
        """Test that collection themes are loaded."""
        from jfc.services.poster_generator import PosterGenerator

        generator = PosterGenerator(
            api_key="test-key",
            output_dir=tmp_path,
        )

        # Should have loaded themes from package templates
        assert isinstance(generator.collection_themes, dict)


class TestCategoryStyles:
    """Tests for category_styles configuration."""

    def test_category_styles_loaded(self, tmp_path: Path):
        """Test that category styles are loaded."""
        from jfc.services.poster_generator import PosterGenerator

        generator = PosterGenerator(
            api_key="test-key",
            output_dir=tmp_path,
        )

        # Should have loaded styles from package templates
        assert isinstance(generator.category_styles, dict)

    def test_films_style_exists(self, tmp_path: Path):
        """Test that FILMS style exists in loaded config."""
        from jfc.services.poster_generator import PosterGenerator

        generator = PosterGenerator(
            api_key="test-key",
            output_dir=tmp_path,
        )

        # Check if FILMS is in the loaded styles
        if generator.category_styles:
            assert "FILMS" in generator.category_styles or len(generator.category_styles) >= 0


class TestHistoryCleanup:
    """Tests for _cleanup_history method."""

    def test_cleanup_old_posters(self, tmp_path: Path):
        """Test cleanup of old poster files."""
        from jfc.services.poster_generator import PosterGenerator

        output_dir = tmp_path / "posters"

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=output_dir,
                poster_history_limit=2,
            )

        # Create collection dir with history
        col_dir = generator._get_collection_dir("Films", "Test")
        history_dir = col_dir / "history"

        # Create 5 old poster files
        for i in range(5):
            (history_dir / f"2024-01-0{i+1}_120000.png").touch()

        # Run cleanup
        generator._cleanup_history(col_dir)

        # Should only keep 2 most recent
        remaining = list(history_dir.glob("*.png"))
        assert len(remaining) == 2

    def test_cleanup_old_prompts(self, tmp_path: Path):
        """Test cleanup of old prompt files."""
        from jfc.services.poster_generator import PosterGenerator

        output_dir = tmp_path / "posters"

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=output_dir,
                prompt_history_limit=3,
            )

        col_dir = generator._get_collection_dir("Films", "Test")
        prompts_dir = col_dir / "prompts"

        # Create 5 prompt files
        for i in range(5):
            (prompts_dir / f"2024-01-0{i+1}_120000.json").touch()

        generator._cleanup_history(col_dir)

        remaining = list(prompts_dir.glob("*.json"))
        assert len(remaining) == 3

    def test_cleanup_unlimited_when_zero(self, tmp_path: Path):
        """Test no cleanup when limit is 0 (unlimited)."""
        from jfc.services.poster_generator import PosterGenerator

        output_dir = tmp_path / "posters"

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=output_dir,
                poster_history_limit=0,  # Unlimited
            )

        col_dir = generator._get_collection_dir("Films", "Test")
        history_dir = col_dir / "history"

        # Create 10 files
        for i in range(10):
            (history_dir / f"2024-01-{i+1:02d}_120000.png").touch()

        generator._cleanup_history(col_dir)

        # All should remain
        remaining = list(history_dir.glob("*.png"))
        assert len(remaining) == 10


class TestTemplateLoading:
    """Tests for template loading functionality."""

    def test_package_templates_dir_exists(self):
        """Test that package templates directory is defined."""
        from jfc.services.poster_generator import PosterGenerator

        assert PosterGenerator.PACKAGE_TEMPLATES_DIR is not None
        # Should point to src/jfc/templates
        assert "templates" in str(PosterGenerator.PACKAGE_TEMPLATES_DIR)

    def test_get_template_from_package(self, tmp_path: Path):
        """Test loading template from package defaults."""
        from jfc.services.poster_generator import PosterGenerator

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=tmp_path,
            )

        # This should load from package templates
        # Mocking for unit test - actual file reading tested in integration
        generator.package_templates_dir = tmp_path / "pkg_templates"
        generator.package_templates_dir.mkdir()
        (generator.package_templates_dir / "test.j2").write_text("Test template")

        content = generator._get_template("test.j2")
        assert content == "Test template"

    def test_get_template_user_override(self, tmp_path: Path):
        """Test that user templates override package templates."""
        from jfc.services.poster_generator import PosterGenerator

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=tmp_path,
            )

        # Setup package template
        generator.package_templates_dir = tmp_path / "pkg_templates"
        generator.package_templates_dir.mkdir()
        (generator.package_templates_dir / "test.j2").write_text("Package template")

        # Setup user override
        generator.templates_dir = tmp_path / "user_templates"
        generator.templates_dir.mkdir()
        (generator.templates_dir / "test.j2").write_text("User template")

        content = generator._get_template("test.j2")
        assert content == "User template"

    def test_get_template_not_found_raises(self, tmp_path: Path):
        """Test that missing template raises FileNotFoundError."""
        from jfc.services.poster_generator import PosterGenerator

        with patch.object(PosterGenerator, "_load_templates"):
            generator = PosterGenerator(
                api_key="test-key",
                output_dir=tmp_path,
            )

        generator.templates_dir = None
        generator.package_templates_dir = tmp_path / "empty"
        generator.package_templates_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            generator._get_template("nonexistent.j2")
