# OAuth Providers Setup Guide for CocktailDB

This document provides detailed instructions for setting up OAuth identity providers (Google, Amazon) for the CocktailDB application. The infrastructure has been pre-configured to support these providers - you just need to obtain the necessary credentials and configure them during deployment.

## Overview

The CocktailDB now supports:
- **Self-registration** (already active)
- **Google OAuth** (requires setup)
- **Amazon Login** (requires setup)

Each OAuth provider is optional and can be enabled independently by providing the appropriate credentials.

---

## 1. Google OAuth Setup

### Prerequisites
- Google Account
- Access to Google Cloud Console

### Step 1: Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "New Project" or select an existing project
3. Note your Project ID for reference

### Step 2: Enable Required APIs
1. In Google Cloud Console, go to **APIs & Services > Library**
2. Search for and enable:
   - **Google+ API** (for user profile information)
   - **People API** (recommended for better user data)

### Step 3: Configure OAuth Consent Screen
1. Go to **APIs & Services > OAuth consent screen**
2. Choose **External** user type (unless using Google Workspace)
3. Fill in required information:
   - **App name**: "CocktailDB" 
   - **User support email**: Your email
   - **Developer contact information**: Your email
   - **App domain**: Your production domain (e.g., `mixology.tools`)
   - **Authorized domains**: Add your domain without protocol
4. Add scopes:
   - `../auth/userinfo.email`
   - `../auth/userinfo.profile`
   - `openid`
5. Save and continue

### Step 4: Create OAuth 2.0 Credentials
1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth 2.0 Client IDs**
3. Choose **Web application**
4. Configure:
   - **Name**: "CocktailDB Web Client"
   - **Authorized JavaScript origins**:
     - Dev: `https://your-cloudfront-domain.cloudfront.net`
     - Prod: `https://mixology.tools` (your domain)
   - **Authorized redirect URIs**:
     - Dev: `https://cocktaildbauth-dev-123456789.auth.us-west-2.amazoncognito.com/oauth2/idpresponse`
     - Prod: `https://auth.mixology.tools/oauth2/idpresponse`
5. Save and note the **Client ID** and **Client Secret**

### Step 5: Deploy with Google OAuth
```bash
# For development
sam deploy --parameter-overrides \
  Environment=dev \
  GoogleClientId="your-google-client-id.apps.googleusercontent.com" \
  GoogleClientSecret="your-google-client-secret"

# For production  
sam deploy --parameter-overrides \
  Environment=prod \
  GoogleClientId="your-google-client-id.apps.googleusercontent.com" \
  GoogleClientSecret="your-google-client-secret" \
  HostedZoneId="your-route53-zone-id"
```

---

## 2. Amazon Login Setup

### Prerequisites
- Amazon Developer Account (free)

### Step 1: Register Security Profile
1. Go to [Amazon Developer Console](https://developer.amazon.com/)
2. Click **Login with Amazon** and then **Create a New Security Profile**
3. Fill in:
   - **Security Profile Name**: "CocktailDB"
   - **Security Profile Description**: "OAuth for CocktailDB application"
   - **Consent Privacy Notice URL**: Link to your privacy policy
   - **Consent Logo Image**: Upload your app logo (114x114px)

### Step 2: Configure Web Settings
1. After creating the profile, click **Web Settings**
2. Configure:
   - **Allowed Origins**:
     - Dev: `https://your-cloudfront-domain.cloudfront.net`
     - Prod: `https://mixology.tools`
   - **Allowed Return URLs**:
     - Dev: `https://cocktaildbauth-dev-123456789.auth.us-west-2.amazoncognito.com/oauth2/idpresponse`
     - Prod: `https://auth.mixology.tools/oauth2/idpresponse`
3. Save settings

### Step 3: Get Credentials
1. Note the **Client ID** and **Client Secret** from the security profile

### Step 4: Deploy with Amazon Login
```bash
sam deploy --parameter-overrides \
  Environment=dev \
  AmazonClientId="amzn1.application-oa2-client.your-client-id" \
  AmazonClientSecret="your-amazon-client-secret"
```

---

## 3. Complete Multi-Provider Setup

You can enable all providers simultaneously:

```bash
# Development with both providers
sam deploy --parameter-overrides \
  Environment=dev \
  GoogleClientId="your-google-client-id.apps.googleusercontent.com" \
  GoogleClientSecret="your-google-client-secret" \
  AmazonClientId="amzn1.application-oa2-client.your-client-id" \
  AmazonClientSecret="your-amazon-client-secret"

# Production with both providers
sam deploy --parameter-overrides \
  Environment=prod \
  HostedZoneId="your-route53-zone-id" \
  GoogleClientId="your-google-client-id.apps.googleusercontent.com" \
  GoogleClientSecret="your-google-client-secret" \
  AmazonClientId="amzn1.application-oa2-client.your-client-id" \
  AmazonClientSecret="your-amazon-client-secret"
```

---

## 4. Testing OAuth Integration

### After Deployment

1. **Access the application** at your domain
2. **Click "Login"** - you should see the Cognito hosted UI
3. **Verify providers appear** - enabled OAuth providers will show as buttons
4. **Test each provider**:
   - Click the provider button
   - Complete authentication on the provider's site
   - Verify you're redirected back and logged in
   - Check that user profile information is correctly mapped

### Troubleshooting Common Issues

#### Google OAuth Issues
- **"redirect_uri_mismatch"**: Check authorized redirect URIs in Google Console
- **"invalid_client"**: Verify Client ID and Secret are correct
- **Consent screen not verified**: Submit for verification if using external users


#### Amazon Login Issues
- **"redirect_uri_mismatch"**: Check allowed return URLs in Amazon Developer Console
- **"invalid_client"**: Verify Client ID and Secret

#### General Cognito Issues
- **Identity provider not found**: Check that parameters are correctly passed to deployment
- **Attribute mapping errors**: Verify user pool attribute configuration
- **Token issues**: Check OAuth scopes and flows configuration

---

## 5. Security Considerations

### Production Recommendations

1. **Use different credentials** for dev and prod environments
2. **Rotate secrets regularly** - Google and Amazon client secrets
3. **Monitor authentication logs** in CloudWatch
4. **Enable advanced security features** in Cognito (if needed)
5. **Implement rate limiting** on authentication endpoints

### Domain Configuration

- **Development**: Uses auto-generated Cognito domain
- **Production**: Uses custom domain (`auth.mixology.tools`)
- Ensure SSL certificates are properly configured for custom domains

---

## 6. Maintenance

### Regular Tasks
- **Monitor OAuth provider documentation** for changes
- **Update redirect URIs** when domain changes
- **Review user analytics** to see which providers are most popular

### Credential Management
- Store production credentials securely (consider AWS Secrets Manager for automation)
- Document credential rotation procedures
- Maintain separate dev/staging/prod configurations

---

## 7. Support and Resources

### Documentation Links
- [AWS Cognito User Pool Identity Providers](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-identity-provider.html)
- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Amazon Login Documentation](https://developer.amazon.com/docs/login-with-amazon/documentation-overview.html)

### Getting Help
- **AWS Support**: For Cognito-related issues
- **Provider Support**: Contact each OAuth provider for their specific issues
- **CloudFormation Documentation**: For template configuration questions

---

*This guide assumes you have already deployed the updated CloudFormation template with OAuth support. If you haven't deployed yet, run the deployment command first with just the basic parameters to enable self-registration, then add OAuth providers incrementally.*