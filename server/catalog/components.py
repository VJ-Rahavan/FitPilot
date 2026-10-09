"""The UI component catalog.

This is the contract between the LLM and the frontend: the LLM may only emit these
components (validated here), and the frontend has one renderer per `type`. The LLM never
produces HTML/JS, so generated UI is always safe and on-brand.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Scalar = str | int | float | bool | None
Icon = Literal[
    "dumbbell",
    "flame",
    "trophy",
    "activity",
    "scale",
    "calendar",
    "timer",
    "heart",
    "target",
    "zap",
]


class _Model(BaseModel):
    # Ignore unknown keys: LLMs occasionally add extras, which shouldn't fail rendering.
    model_config = ConfigDict(extra="ignore")


# --------------------------------------------------------------------------- primitives


class TextComponent(_Model):
    """Markdown text. Use variant 'heading' / 'subheading' for section titles."""

    type: Literal["text"]
    content: str = Field(min_length=1, description="Markdown content")
    variant: Literal["body", "heading", "subheading", "muted"] = "body"


class MetricComponent(_Model):
    """A single headline number (KPI tile)."""

    type: Literal["metric"]
    label: str
    value: str | int | float
    unit: str | None = None
    change_pct: float | None = Field(None, description="Percent change vs previous period")
    good_direction: Literal["up", "down"] = Field(
        "up",
        description="Direction of change that is good for the user: 'up' for sessions, volume, "
        "strength, streaks; 'down' only for things like body weight/fat on a cut",
    )
    caption: str | None = None
    icon: Icon | None = None


class CardComponent(_Model):
    """A titled container for other components."""

    type: Literal["card"]
    title: str | None = None
    description: str | None = None
    children: list["Component"] = Field(default_factory=list)


class LayoutComponent(_Model):
    """Arrange children in a row, column or responsive grid."""

    type: Literal["layout"]
    direction: Literal["row", "column", "grid"] = "column"
    columns: int = Field(2, ge=1, le=4, description="Number of grid columns (grid only)")
    children: list["Component"] = Field(min_length=1)


class TableColumn(_Model):
    key: str
    label: str
    align: Literal["left", "center", "right"] = "left"


class TableComponent(_Model):
    type: Literal["table"]
    title: str | None = None
    columns: list[TableColumn] = Field(min_length=1)
    rows: list[dict[str, Scalar]] = Field(description="Objects keyed by column key")


class ChartSeries(_Model):
    key: str = Field(description="Key in each data row holding this series' numeric value")
    label: str | None = None


class ChartComponent(_Model):
    """Line/bar/area chart or pie chart from flat data rows."""

    type: Literal["chart"]
    chart_type: Literal["line", "bar", "area", "pie"]
    title: str | None = None
    description: str | None = None
    data: list[dict[str, Scalar]] = Field(min_length=1, description="Flat objects, one per x value")
    x_key: str = Field(description="Key for the x-axis category (or pie slice label)")
    series: list[ChartSeries] = Field(min_length=1, description="Pie charts use one series")
    unit: str | None = Field(None, description="Unit appended to values, e.g. 'kg'")

    @model_validator(mode="after")
    def _keys_exist(self) -> "ChartComponent":
        keys = {k for row in self.data for k in row}
        missing = [k for k in [self.x_key, *(s.key for s in self.series)] if k not in keys]
        if missing:
            raise ValueError(
                f"keys {missing} not found in data rows (available keys: {sorted(keys)})"
            )
        return self


class ListItem(_Model):
    title: str
    description: str | None = None
    badge: str | None = None


class ListComponent(_Model):
    type: Literal["list"]
    title: str | None = None
    ordered: bool = False
    items: list[ListItem] = Field(min_length=1)


class AlertComponent(_Model):
    type: Literal["alert"]
    variant: Literal["info", "success", "warning", "error"] = "info"
    title: str | None = None
    message: str


class ProgressComponent(_Model):
    """Progress bar toward a goal."""

    type: Literal["progress"]
    label: str
    value: float
    max: float = Field(100, gt=0)
    unit: str | None = None
    caption: str | None = None


# --------------------------------------------------------------------------- interactive


class ButtonComponent(_Model):
    """Clicking sends `action` + `payload` back to the assistant as a UI event."""

    type: Literal["button"]
    label: str
    action: str = Field(description="snake_case action name, e.g. 'show_progress'")
    payload: dict[str, Any] = Field(default_factory=dict)
    variant: Literal["primary", "secondary", "ghost", "danger"] = "primary"


class SelectOption(_Model):
    label: str
    value: str | int | float


class FormField(_Model):
    name: str
    label: str
    input: Literal["text", "number", "email", "textarea", "select", "checkbox", "date"] = "text"
    placeholder: str | None = None
    required: bool = False
    default: Scalar = None
    options: list[SelectOption] | None = Field(None, description="Required for 'select'")
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def _select_needs_options(self) -> "FormField":
        if self.input == "select" and not self.options:
            raise ValueError("select fields require non-empty 'options'")
        return self


class FormComponent(_Model):
    """Submitting sends `action` with {field name: value} back to the assistant."""

    type: Literal["form"]
    title: str | None = None
    description: str | None = None
    fields: list[FormField] = Field(min_length=1)
    submit_label: str = "Submit"
    action: str = Field(description="snake_case action name, e.g. 'calculate_macros'")


# --------------------------------------------------------------------------- fitness


class ExerciseCardComponent(_Model):
    """How-to card for a single exercise."""

    type: Literal["exercise_card"]
    name: str
    primary_muscles: list[str] = Field(min_length=1)
    secondary_muscles: list[str] = Field(default_factory=list)
    equipment: str | None = None
    difficulty: Literal["beginner", "intermediate", "advanced"] | None = None
    instructions: list[str] = Field(min_length=1)
    tips: list[str] = Field(default_factory=list)


class PlanExercise(_Model):
    name: str
    sets: int = Field(ge=1, le=20)
    reps: str = Field(description="Rep target, e.g. '8-12' or '5'")
    rest_seconds: int | None = None
    notes: str | None = None


class PlanDay(_Model):
    day: str = Field(description="e.g. 'Day 1' or 'Monday'")
    focus: str = Field(description="e.g. 'Upper body — push'")
    exercises: list[PlanExercise] = Field(min_length=1)


class WorkoutPlanComponent(_Model):
    """A multi-day training program."""

    type: Literal["workout_plan"]
    title: str
    goal: str | None = None
    weeks: int | None = Field(None, ge=1, le=52)
    days: list[PlanDay] = Field(min_length=1)


class TimerComponent(_Model):
    """Client-side countdown, e.g. for rest periods or planks."""

    type: Literal["timer"]
    label: str = "Rest timer"
    seconds: int = Field(ge=5, le=3600)


# --------------------------------------------------------------------------- union

Component = Annotated[
    TextComponent
    | MetricComponent
    | CardComponent
    | LayoutComponent
    | TableComponent
    | ChartComponent
    | ListComponent
    | AlertComponent
    | ProgressComponent
    | ButtonComponent
    | FormComponent
    | ExerciseCardComponent
    | WorkoutPlanComponent
    | TimerComponent,
    Field(discriminator="type"),
]

CardComponent.model_rebuild()
LayoutComponent.model_rebuild()


class UISpec(_Model):
    """Arguments of the `render_ui` tool: an ordered list of top-level components."""

    components: list[Component] = Field(min_length=1, max_length=40)
