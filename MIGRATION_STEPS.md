# Migration Instructions

## Issue
The database table `store_settings_consolidated` doesn't exist yet. You need to create and run migrations.

## Steps to Fix

### 1. Create Migration
```bash
python manage.py makemigrations store_settings
```

This will create a new migration file for the consolidated StoreSettings model.

### 2. Apply Migration to Shared Schema
```bash
python manage.py migrate_schemas --shared
```

This applies the migration to the public/shared schema.

### 3. Apply Migration to All Tenants
```bash
python manage.py migrate_schemas
```

This applies the migration to all tenant schemas.

### 4. Restart Server
After migrations are complete, restart your server:
```bash
python manage.py runserver 2000
```

## Alternative: Quick Test

If you just want to test quickly on the current tenant:
```bash
python manage.py migrate
```

Then access: `http://localhost:2000/dashboard/settings/`

## What This Does

The migration will:
- Create the new `store_settings_consolidated` table
- Add all 100+ fields for the comprehensive settings
- Set up proper indexes and constraints

## After Migration

Once the table is created, the settings page will:
1. Automatically create a default settings instance
2. Show the professional UI with tabs
3. Allow you to configure all store settings

## Troubleshooting

If you get errors:
- **"No changes detected"**: The migration already exists, skip to step 2
- **"Table already exists"**: Run `python manage.py migrate --fake` to mark as applied
- **Permission errors**: Check database user permissions
