# EXTRACTION-ONLY POLICY (NEVER SEND OUTBOUND EMAILS)

## Critical Operational Rule
This pipeline is **strictly an incoming extraction tool**.
It extracts requirements from incoming emails received in Microsoft Outlook.

### Strict Prohibitions
1. **NEVER send outbound emails**:
   - The system must NEVER send any email through Microsoft Graph API, SMTP, or any other protocol.
   - Any alert, notification, test probe, candidate notice, or operational report MUST NEVER be sent via email.
2. **Prohibited Address**:
   - NEVER send anything to `recruitment.application@metaforgeit.com` or any `@metaforgeit.com` mailbox.
3. **Extraction Only**:
   - The mailbox credentials and Microsoft Graph access are strictly READ-ONLY for reading and extracting incoming demand emails.
   - All alerts and operational metrics must be recorded locally in the database/UI, never dispatched as outbound emails.
