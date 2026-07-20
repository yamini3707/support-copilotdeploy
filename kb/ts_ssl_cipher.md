---
doc_id: ts_ssl_cipher
title: ERR_SSL_VERSION_OR_CIPHER_MISMATCH when calling the API
doc_type: troubleshooting
plan: all
version: v1
date: 2026-03-15
---

# ERR_SSL_VERSION_OR_CIPHER_MISMATCH when calling the API

If you encounter the error `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` while calling the CloudDesk API, it indicates a problem with the TLS version or cipher suite being used by your client. This error typically arises when the client attempts to connect using an outdated TLS version or a cipher suite that is no longer supported by the server.

To resolve this issue, ensure that your client is configured to use TLS 1.2 or higher. Most modern programming languages and libraries support this version, but you may need to explicitly enable it in your configuration settings. 

Additionally, verify that your system's libraries and dependencies are up to date, as older versions may not support the required protocols. After making these changes, try calling the API again. If the issue persists, consider checking your network settings or consulting your system administrator for further assistance.
