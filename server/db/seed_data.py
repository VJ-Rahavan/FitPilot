"""Static seed data: exercise catalog and the demo user's 4-day plan."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExerciseSeed:
    name: str
    equipment: str
    aliases: tuple[str, ...]
    form_cues: tuple[str, ...]


EXERCISES: tuple[ExerciseSeed, ...] = (
    ExerciseSeed(
        "Back Squat",
        "barbell",
        ("squat", "barbell squat", "back squats"),
        (
            "Brace your core before you descend.",
            "Knees track over your toes.",
            "Drive up through the whole foot.",
        ),
    ),
    ExerciseSeed(
        "Front Squat",
        "barbell",
        ("front squats", "barbell front squat"),
        (
            "Keep your elbows high.",
            "Stay upright through the whole rep.",
            "Sit straight down between your heels.",
        ),
    ),
    ExerciseSeed(
        "Bench Press",
        "barbell",
        ("bench", "flat bench", "barbell bench press", "flat bench press"),
        (
            "Pull your shoulder blades back and down.",
            "Lower the bar to mid chest.",
            "Keep your feet planted and drive through the floor.",
        ),
    ),
    ExerciseSeed(
        "Incline Bench Press",
        "barbell",
        ("incline bench", "incline press", "incline barbell press"),
        (
            "Set the bench to about 30 degrees.",
            "Touch the bar just below your collarbone.",
            "Keep your wrists stacked over your elbows.",
        ),
    ),
    ExerciseSeed(
        "Overhead Press",
        "barbell",
        ("ohp", "military press", "shoulder press", "standing press"),
        (
            "Squeeze your glutes to protect your lower back.",
            "Move your head back, then through, as the bar passes.",
            "Lock out with the bar over your mid foot.",
        ),
    ),
    ExerciseSeed(
        "Deadlift",
        "barbell",
        ("deadlifts", "conventional deadlift", "dead lift"),
        (
            "Bar over mid foot before you pull.",
            "Take the slack out of the bar first.",
            "Keep the bar close and push the floor away.",
        ),
    ),
    ExerciseSeed(
        "Romanian Deadlift",
        "barbell",
        ("rdl", "romanian dl", "stiff leg deadlift"),
        (
            "Push your hips back, not down.",
            "Soft knees, flat back.",
            "Stop when your hamstrings are fully stretched.",
        ),
    ),
    ExerciseSeed(
        "Barbell Row",
        "barbell",
        ("row", "bent over row", "bent row", "bb row"),
        (
            "Hinge until your torso is close to parallel.",
            "Pull the bar to your lower ribs.",
            "Don't use your hips to swing the weight.",
        ),
    ),
    ExerciseSeed(
        "Pull-Up",
        "bodyweight",
        ("pullup", "pull up", "pullups"),
        (
            "Start from a dead hang.",
            "Drive your elbows down to your ribs.",
            "Get your chin over the bar without craning your neck.",
        ),
    ),
    ExerciseSeed(
        "Chin-Up",
        "bodyweight",
        ("chinup", "chin up", "chinups"),
        (
            "Use a shoulder-width underhand grip.",
            "Pull your chest toward the bar.",
            "Control the way down.",
        ),
    ),
    ExerciseSeed(
        "Lat Pulldown",
        "cable",
        ("pulldown", "lat pull down", "lat pulldowns"),
        (
            "Lean back slightly.",
            "Pull the bar to your upper chest.",
            "Let your arms fully extend at the top.",
        ),
    ),
    ExerciseSeed(
        "Seated Cable Row",
        "cable",
        ("cable row", "seated row"),
        (
            "Sit tall with a neutral spine.",
            "Lead with your elbows.",
            "Squeeze your shoulder blades together at the end.",
        ),
    ),
    ExerciseSeed(
        "Dumbbell Bench Press",
        "dumbbell",
        ("db bench", "dumbbell bench", "db bench press"),
        (
            "Lower the dumbbells to chest level.",
            "Press up and slightly in.",
            "Keep your shoulder blades pinned.",
        ),
    ),
    ExerciseSeed(
        "Dumbbell Shoulder Press",
        "dumbbell",
        ("db shoulder press", "seated dumbbell press", "dumbbell overhead press"),
        (
            "Start with the dumbbells at ear height.",
            "Press straight up without arching.",
            "Keep your ribs down.",
        ),
    ),
    ExerciseSeed(
        "Dumbbell Curl",
        "dumbbell",
        ("curl", "bicep curl", "biceps curl", "db curl"),
        ("Keep your elbows pinned to your sides.", "Don't swing your torso.", "Lower slowly."),
    ),
    ExerciseSeed(
        "Hammer Curl",
        "dumbbell",
        ("hammer curls", "neutral grip curl"),
        ("Thumbs up the whole time.", "Elbows stay still.", "Control the lowering."),
    ),
    ExerciseSeed(
        "Triceps Pushdown",
        "cable",
        ("tricep pushdown", "pushdown", "rope pushdown", "cable pushdown"),
        (
            "Elbows stay tight to your sides.",
            "Fully straighten your arms.",
            "Let the rope come up slowly.",
        ),
    ),
    ExerciseSeed(
        "Skull Crusher",
        "barbell",
        ("skullcrusher", "lying triceps extension", "ez bar skull crusher"),
        (
            "Lower the bar toward your forehead.",
            "Keep your upper arms still.",
            "Use a weight you can control.",
        ),
    ),
    ExerciseSeed(
        "Dip",
        "bodyweight",
        ("dips", "chest dip", "parallel bar dip"),
        (
            "Lean slightly forward.",
            "Go down until your shoulders are just below your elbows.",
            "Lock out at the top.",
        ),
    ),
    ExerciseSeed(
        "Leg Press",
        "machine",
        ("leg presses", "sled press"),
        (
            "Feet shoulder-width on the platform.",
            "Don't let your lower back lift off the pad.",
            "Don't lock your knees at the top.",
        ),
    ),
    ExerciseSeed(
        "Leg Curl",
        "machine",
        ("hamstring curl", "lying leg curl", "seated leg curl"),
        ("Keep your hips pressed into the pad.", "Curl all the way in.", "Lower slowly."),
    ),
    ExerciseSeed(
        "Leg Extension",
        "machine",
        ("quad extension", "leg extensions"),
        (
            "Line your knee up with the machine's pivot.",
            "Pause at the top.",
            "Lower under control.",
        ),
    ),
    ExerciseSeed(
        "Standing Calf Raise",
        "machine",
        ("calf raise", "calf raises", "calves"),
        ("Full stretch at the bottom.", "Pause at the top.", "Keep your knees straight."),
    ),
    ExerciseSeed(
        "Bulgarian Split Squat",
        "dumbbell",
        ("split squat", "bss", "rear foot elevated split squat"),
        (
            "Most of your weight on the front leg.",
            "Drop your back knee straight down.",
            "Keep your torso tall.",
        ),
    ),
    ExerciseSeed(
        "Hip Thrust",
        "barbell",
        ("hip thrusts", "barbell hip thrust", "glute bridge"),
        (
            "Upper back on the bench edge.",
            "Tuck your chin and ribs.",
            "Squeeze your glutes hard at the top.",
        ),
    ),
    ExerciseSeed(
        "Lateral Raise",
        "dumbbell",
        ("lateral raises", "side raise", "side lateral raise"),
        ("Lead with your elbows.", "Raise to shoulder height.", "Don't shrug."),
    ),
    ExerciseSeed(
        "Hanging Leg Raise",
        "bodyweight",
        ("leg raise", "leg raises", "hanging knee raise"),
        ("Avoid swinging.", "Curl your pelvis up at the top.", "Lower slowly."),
    ),
    ExerciseSeed(
        "Push-Up",
        "bodyweight",
        ("pushup", "push up", "pushups", "press up"),
        (
            "Body in one straight line.",
            "Elbows at about 45 degrees.",
            "Chest all the way to the floor.",
        ),
    ),
)


@dataclass(frozen=True)
class PlanExerciseSeed:
    exercise: str
    sets: int
    reps: int
    start_weight_lb: float  # 8 weeks ago; 0 for bodyweight


# Mon / Tue / Thu / Fri upper-lower split. Weekday 0 = Monday.
PLAN_NAME = "4-Day Upper/Lower Strength"
PLAN_DAYS: tuple[tuple[str, int, tuple[PlanExerciseSeed, ...]], ...] = (
    (
        "Upper A",
        0,
        (
            PlanExerciseSeed("Bench Press", 4, 6, 165),
            PlanExerciseSeed("Barbell Row", 4, 8, 135),
            PlanExerciseSeed("Overhead Press", 3, 8, 95),
            PlanExerciseSeed("Lat Pulldown", 3, 10, 120),
            PlanExerciseSeed("Dumbbell Curl", 3, 12, 25),
        ),
    ),
    (
        "Lower A",
        1,
        (
            PlanExerciseSeed("Back Squat", 4, 6, 205),
            PlanExerciseSeed("Romanian Deadlift", 3, 8, 165),
            PlanExerciseSeed("Leg Press", 3, 10, 290),
            PlanExerciseSeed("Leg Curl", 3, 12, 80),
            PlanExerciseSeed("Standing Calf Raise", 3, 15, 140),
        ),
    ),
    (
        "Upper B",
        3,
        (
            PlanExerciseSeed("Incline Bench Press", 4, 8, 135),
            PlanExerciseSeed("Pull-Up", 4, 6, 0),
            PlanExerciseSeed("Dumbbell Shoulder Press", 3, 10, 40),
            PlanExerciseSeed("Seated Cable Row", 3, 10, 120),
            PlanExerciseSeed("Triceps Pushdown", 3, 12, 50),
        ),
    ),
    (
        "Lower B",
        4,
        (
            PlanExerciseSeed("Deadlift", 3, 5, 255),
            PlanExerciseSeed("Front Squat", 3, 6, 135),
            PlanExerciseSeed("Bulgarian Split Squat", 3, 8, 30),
            PlanExerciseSeed("Hip Thrust", 3, 10, 185),
            PlanExerciseSeed("Hanging Leg Raise", 3, 12, 0),
        ),
    ),
)
