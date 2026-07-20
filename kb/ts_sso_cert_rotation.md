---
doc_id: ts_sso_cert_rotation
title: SAML login fails after certificate rotation
doc_type: troubleshooting
plan: all
version: v1
date: 2026-03-15
---

# SAML Login Fails After Certificate Rotation

If you're experiencing issues with SAML login in CloudDesk after your Identity Provider (IdP) has rotated its signing certificate, you may encounter an error stating that the "signature invalid." This occurs because CloudDesk continues to validate SAML assertions against the old certificate until the IdP metadata is updated.

To resolve this issue, follow these steps:

1. **Re-upload IdP Metadata**: Obtain the latest IdP metadata file that includes the new signing certificate. In CloudDesk, navigate to the SSO settings and upload the updated metadata.

2. **Clear SSO Cache**: After updating the metadata, it's essential to clear the SSO cache. This ensures that CloudDesk no longer references the old signing certificate. You can do this by going to the SSO settings and selecting the option to clear the cache.

3. **Re-Test the SAML Login**: Once the cache is cleared, attempt to log in again using SAML. The new signing certificate should now be recognized, and the "signature invalid" error should be resolved.

By following these steps, you can successfully restore SAML login functionality in CloudDesk after a certificate rotation.
