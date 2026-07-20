---
doc_id: sso_setup_guide
title: SSO Setup & Troubleshooting (SAML / OIDC)
category: technical
---

# SSO Setup & Troubleshooting

Single Sign-On is available on **Business and Enterprise** plans. Pro and Free plans do not
include SSO; customers on those plans must upgrade to enable it.

## Setting up SAML SSO

1. In **Admin → Security → SSO**, choose SAML 2.0.
2. Copy the CloudDesk **ACS URL** and **Entity ID** into your identity provider (IdP).
3. Upload your IdP **metadata XML** (or paste the metadata URL) back into CloudDesk.
4. Map the `email` and `name` attributes.
5. Enable **Test mode**, verify one login, then enforce SSO for the organization.

## Setting up OIDC

Provide the **client ID**, **client secret**, and **discovery URL** from your IdP. CloudDesk
uses the authorization-code flow. Redirect URIs must exactly match, including trailing slashes.

## Troubleshooting: logins failing after certificate rotation

The most common SSO failure is an **expired or rotated signing certificate**. When your IdP
rotates its SAML signing certificate, CloudDesk continues to validate against the old
certificate until you update the metadata. Symptoms: users see "SAML response signature
invalid" or are bounced back to the login screen.

To fix:

1. In your IdP, export the **new** signing certificate / updated metadata.
2. In **Admin → Security → SSO**, re-upload the metadata XML (or refresh the metadata URL).
3. Clear the SSO session cache (**Admin → Security → SSO → Clear cache**).
4. Re-test in Test mode before re-enforcing.

If logins still fail after re-uploading metadata, check the CloudDesk **status page for any
active SSO incident** before escalating — a platform-side incident can cause the same symptoms.
If there is no active incident and metadata is confirmed current, escalate to the platform team.
