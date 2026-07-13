from marketing.models import SocialProfileSettings


def social_profiles(request):
    return {"social_profiles": SocialProfileSettings.load()}
