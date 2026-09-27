import pytest


@pytest.fixture
def buyer_post():
    """Real post that the old rubric scored 3. A 60-ball order."""
    return {
        "url": "https://fb.com/p/buyer",
        "facebookUrl": "https://fb.com/groups/1061644604326919",
        "text": ("רוצה ליסוע לצפון בראשון לעשות ל 100 לוחמים מילואימניקים פיצות בטאבון "
                 "יש את כל המסביב מחפש מישהו שמוכר 50-60 כדורי פיצה לטאבון 300g אשמח לעזרה"),
        "user": {"name": "מאיר"},
        "time": "2026-09-16",
        "topComments": [],
    }


@pytest.fixture
def theory_post():
    """Real post that the old rubric scored 8. High expertise, zero lead."""
    return {
        "url": "https://fb.com/p/theory",
        "facebookUrl": "https://fb.com/groups/587379969063560",
        "text": "לחם מחמצת. מה הסיפור? מה זה בכלל מחמצת? אשמח לכל התובנות שלכם 🤍 תודה.",
        "user": {"name": "רונית"},
        "time": "2026-09-16",
        "topComments": [],
    }


@pytest.fixture
def cooking_post():
    """Real post Gilad rejected: new tabun owner, but asking what to COOK."""
    return {
        "url": "https://fb.com/p/cooking",
        "facebookUrl": "https://fb.com/groups/2926500980956274",
        "text": ("רכשנו טאבון גז cozzi עם צלחת מסתובבת . ממה מתחילים ? ירקות ? "
                 "אשמח לטיפים עבור מתחילים . תודה וחג שמח"),
        "user": {"name": "אורית"},
        "time": "2026-09-16",
        "topComments": [],
    }
