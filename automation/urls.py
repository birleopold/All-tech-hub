from django.urls import path

from automation import staff_views


urlpatterns = [
    path(
        "automation/",
        staff_views.AutomationControlDashboardView.as_view(),
        name="staff_automation_control",
    ),
    path(
        "automation/social-autopilot/",
        staff_views.social_autopilot_update,
        name="staff_social_autopilot_update",
    ),
    path(
        "automation/social-autopilot/test-connections/",
        staff_views.social_autopilot_test_connections,
        name="staff_social_autopilot_test_connections",
    ),
    path(
        "automation/social-autopilot/posts/<int:post_id>/publish-now/",
        staff_views.social_autopilot_publish_now,
        name="staff_social_autopilot_publish_now",
    ),
    path(
        "automation/social-autopilot/posts/<int:post_id>/cancel/",
        staff_views.social_autopilot_cancel_post,
        name="staff_social_autopilot_cancel_post",
    ),
    path(
        "automation/social-autopilot/rebuild/",
        staff_views.social_autopilot_rebuild,
        name="staff_social_autopilot_rebuild",
    ),
    path(
        "automation/social-autopilot/products/<int:product_id>/promote/",
        staff_views.social_autopilot_promote_product,
        name="staff_social_autopilot_promote_product",
    ),
    path(
        "automation/pause/",
        staff_views.automation_pause,
        name="staff_automation_pause",
    ),
    path(
        "automation/resume/",
        staff_views.automation_resume,
        name="staff_automation_resume",
    ),
    path(
        "automation/jobs/<int:pk>/",
        staff_views.automation_job_detail,
        name="staff_automation_job_detail",
    ),
    path(
        "automation/jobs/<int:pk>/replay/",
        staff_views.automation_job_replay,
        name="staff_automation_job_replay",
    ),
    path(
        "automation/jobs/<int:pk>/cancel/",
        staff_views.automation_job_cancel,
        name="staff_automation_job_cancel",
    ),
]
