# IAM Roles Setup for RELand App Runner Deployment

**Date:** January 16, 2026  
**Account:** 348170387270  
**Region:** us-east-1  
**Project:** RELand Backend Deployment

---

## Overview

App Runner requires **TWO separate IAM roles**:

1. **ECR Access Role** - Allows App Runner to pull Docker images from ECR
2. **Instance Role** - Used by the running App Runner service (for EC2, S3, etc.)

---

## Role 1: ECR Access Role

### Role Name
`reland-apprunner-ecr-role`

### Purpose
Allows App Runner build service to pull Docker images from Amazon ECR.

### Trust Policy (REQUIRED)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "build.apprunner.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### Permissions (Attach these managed policies)
- `AmazonEC2ContainerRegistryReadOnly` (allows pulling images from ECR)

### AWS CLI Commands to Create
```bash
# Create the role with trust policy
aws iam create-role \
  --role-name reland-apprunner-ecr-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "build.apprunner.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  }'

# Attach ECR read-only policy
aws iam attach-role-policy \
  --role-name reland-apprunner-ecr-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
```

### Status
- [ ] **NEEDS TO BE CREATED** (does not exist yet)

---

## Role 2: Instance Role (App Runner Service Role)

### Role Name
`reland-apprunner-role`

### Purpose
Used by the running App Runner service to:
- Launch EC2 instances for ML model training
- Access S3 bucket to read/write ML models
- Access other AWS services as needed

### Current Status
✅ **ALREADY EXISTS** but needs trust policy update

### Current Trust Policy (INCORRECT - needs update)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "tasks.apprunner.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### Required Trust Policy (CORRECT)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "tasks.apprunner.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**Note:** Actually, the current trust policy is CORRECT for the instance role! The issue is that this role is being used in the wrong place. See "Usage" section below.

### Permissions (Should already be attached)
- `AmazonEC2FullAccess` (to launch EC2 workers for ML training)
- `AmazonS3FullAccess` (to access models bucket)
- `AmazonEC2ContainerRegistryReadOnly` (optional, for pulling images - but ECR access role handles this)

### AWS CLI Commands to Verify/Update
```bash
# Check current trust policy
aws iam get-role --role-name reland-apprunner-role --query 'Role.AssumeRolePolicyDocument'

# Update trust policy if needed (should already be correct)
aws iam update-assume-role-policy \
  --role-name reland-apprunner-role \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "tasks.apprunner.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  }'

# Verify permissions are attached
aws iam list-attached-role-policies --role-name reland-apprunner-role
```

### Status
- [x] Role exists
- [ ] Trust policy verified (should be `tasks.apprunner.amazonaws.com`)
- [ ] Permissions verified

---

## Usage in App Runner Console

### When Creating App Runner Service:

**IMPORTANT:** App Runner has TWO separate role configuration sections that appear at DIFFERENT stages:

1. **ECR Access Role Section (Early in Setup - "Deployment settings"):**
   - **When:** Appears when you select ECR as source
   - **Location:** "Deployment settings" → "ECR access role"
   - **Action:** 
     - Select: "Use existing service role"
     - Choose: `reland-apprunner-ecr-role` (needs to be created first)
     - **OR** Select "Create new service role" and App Runner will auto-create one
   - **Note:** If you don't see roles, you may need `iam:ListRoles` permission

2. **Instance Role Section (Later in Configuration - "Configure service"):**
   - **When:** Appears in "Configure service" step, usually under "Security" or "Advanced settings"
   - **Location:** "Configure service" → Scroll down to "Security" or "Instance role"
   - **Action:**
     - Select: "Use existing service role"
     - Choose: `reland-apprunner-role` (already exists, trust policy is correct)
   - **Note:** This section appears AFTER you've configured the ECR access role and container settings

---

## Summary Checklist for AWS Administrator

### Immediate Actions Required:

1. **Create ECR Access Role:**
   - [ ] Create role: `reland-apprunner-ecr-role`
   - [ ] Set trust policy with `build.apprunner.amazonaws.com`
   - [ ] Attach `AmazonEC2ContainerRegistryReadOnly` policy

2. **Verify Instance Role:**
   - [ ] Verify `reland-apprunner-role` exists
   - [ ] Verify trust policy has `tasks.apprunner.amazonaws.com` (should already be correct)
   - [ ] Verify permissions: `AmazonEC2FullAccess`, `AmazonS3FullAccess`

---

## Complete AWS CLI Script for Administrator

```bash
#!/bin/bash
# Run this script as AWS Administrator to set up both roles

ACCOUNT_ID=348170387270
REGION=us-east-1

echo "=== Creating ECR Access Role ==="

# Create ECR access role
aws iam create-role \
  --role-name reland-apprunner-ecr-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "build.apprunner.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  }' \
  --description "App Runner ECR access role for RELand project"

# Attach ECR read-only policy
aws iam attach-role-policy \
  --role-name reland-apprunner-ecr-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly

echo "✅ ECR Access Role created: reland-apprunner-ecr-role"

echo ""
echo "=== Verifying Instance Role ==="

# Check if instance role exists
if aws iam get-role --role-name reland-apprunner-role &>/dev/null; then
    echo "✅ Instance role exists: reland-apprunner-role"
    
    # Verify trust policy
    CURRENT_TRUST=$(aws iam get-role --role-name reland-apprunner-role \
      --query 'Role.AssumeRolePolicyDocument' --output json)
    
    if echo "$CURRENT_TRUST" | grep -q "tasks.apprunner.amazonaws.com"; then
        echo "✅ Trust policy is correct (tasks.apprunner.amazonaws.com)"
    else
        echo "⚠️  Trust policy needs update"
        aws iam update-assume-role-policy \
          --role-name reland-apprunner-role \
          --policy-document '{
            "Version": "2012-10-17",
            "Statement": [
              {
                "Effect": "Allow",
                "Principal": {
                  "Service": "tasks.apprunner.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
              }
            ]
          }'
        echo "✅ Trust policy updated"
    fi
    
    # Verify permissions
    echo "Checking attached policies..."
    aws iam list-attached-role-policies --role-name reland-apprunner-role
else
    echo "❌ Instance role does not exist. Please create reland-apprunner-role first."
fi

echo ""
echo "=== Setup Complete ==="
echo "ECR Access Role: reland-apprunner-ecr-role"
echo "Instance Role: reland-apprunner-role"
```

---

## Troubleshooting

### Issue: ECR Access Role not showing in dropdown
**Solution:** 
- Verify trust policy has `build.apprunner.amazonaws.com` (not `tasks.apprunner.amazonaws.com`)
- Ensure role name is exactly `reland-apprunner-ecr-role`
- Try refreshing the page or clicking the refresh icon next to the dropdown
- **If you see "No match" or empty dropdown:** You may need `iam:ListRoles` permission. Ask administrator to add this permission or use "Create new service role" option

### Issue: Instance Role not showing in dropdown
**Solution:**
- **First, verify you're in the correct section:** The instance role appears LATER in the App Runner setup, not in the ECR access section. Look for "Configure service" → "Security" or "Instance role" section
- Verify trust policy has `tasks.apprunner.amazonaws.com` (not `build.apprunner.amazonaws.com`)
- Ensure role name is exactly `reland-apprunner-role`
- Verify role has required permissions attached (`AmazonEC2FullAccess`, `AmazonS3FullAccess`)
- **If you see "No match" or empty dropdown:** You may need `iam:ListRoles` permission. Ask administrator to add this permission
- **Alternative:** Use "Specify a custom value" and enter: `reland-apprunner-role` manually

### Issue: "User is not authorized to perform: iam:ListRoles"
**Solution:**
- This means your IAM user doesn't have permission to list roles
- Ask administrator to add this permission:
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "iam:ListRoles",
          "iam:ListInstanceProfiles",
          "iam:GetRole"
        ],
        "Resource": "*"
      }
    ]
  }
  ```
- **OR** Use "Specify a custom value" option and manually enter the role name

---

## Reference Links

- [App Runner IAM Roles Documentation](https://docs.aws.amazon.com/apprunner/latest/dg/security-iam-service-with-iam.html)
- [ECR Access Role](https://docs.aws.amazon.com/apprunner/latest/dg/security-iam-service-with-iam.html#security-iam-service-with-iam-roles-ecr)
- [Instance Role](https://docs.aws.amazon.com/apprunner/latest/dg/security-iam-service-with-iam.html#security-iam-service-with-iam-roles-instance)

---

## Contact Information

If you have questions about these roles, please contact the deployment team.

**Last Updated:** January 16, 2026
