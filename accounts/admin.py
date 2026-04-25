from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'name', 'phone', 'place', 'is_admin', 'is_active', 'is_staff', 'date_joined']
    list_filter = ['is_admin', 'is_active', 'is_staff', 'is_superuser']
    search_fields = ['email', 'name', 'phone', 'place']
    ordering = ['-date_joined']
    list_editable = ['is_admin', 'is_active']

    fieldsets = (
        ('Credentials', {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('name', 'phone', 'place')}),
        (
            'Permissions',
            {
                'fields': (
                    'is_admin',
                    'is_active',
                    'is_staff',
                    'is_superuser',
                    'groups',
                    'user_permissions',
                )
            },
        ),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'email',
                    'name',
                    'phone',
                    'place',
                    'password1',
                    'password2',
                    'is_admin',
                    'is_staff',
                ),
            },
        ),
    )

    readonly_fields = ['date_joined', 'last_login']
    filter_horizontal = ['groups', 'user_permissions']
