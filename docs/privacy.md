# Privacy: the engine never knows who a person is

AccessPath is split into parts that never mix:

| Part | Holds | Where it lives |
|---|---|---|
| **Engine** (this repository) | Research library, rules, room checks. Takes only numbers about a body (reach, height band, mobility aid, functional presets) and a room's geometry, keyed by a random client code | The customer's machine today; could run on AccessPath's servers in a future hosted version |
| **Client vault** (not built yet) | Which nickname a client code belongs to, on the computer where the envelope was made | Only that computer, encrypted, never sent anywhere |
| **Account** (not built yet) | Name, contact details and a non-medical job scope, for contractor matching | AccessPath's servers; never linked to a nickname, code or envelope |

The random client code links the engine to the vault, and nothing else. The account holds no code, nickname or envelope, so nothing on AccessPath's servers connects a name to a body.

## Intake: two steps (decided Oct 4, 2026)

1. **Account (AccessPath's servers).** The family's name, contact details and the job scope (what they want done to the house). No medical or functional information: wording stays at "requires accessibility modifications", never "wheelchair user" or a diagnosis. AccessPath sends the name and scope to the matched contractor.
2. **Reach envelope generator (the family's computer).** A generic download with no account ID inside it. It asks for a nickname, never a name; runs the engine locally; and saves the envelope only on that computer. The envelope reaches the contractor either from the family directly or sent straight from the generator to the contractor, encrypted so AccessPath can't read it and with nothing stored on AccessPath's servers.

AccessPath never accepts reach envelopes or medical documents from customers, including for troubleshooting; support gets only the app version and error codes.

## Rules

1. **The engine takes no identifying fields.** `accesspath/privacy.py` rejects names, birthdates, ages, addresses, phone numbers, emails, record or insurance numbers, and diagnoses wherever they would enter: the Profiles sheet's columns and every key of a room file. A test covers each.
2. **Profiles describe function, not diagnosis.** Research cards may name the condition a study measured (that is where the number came from); a client's profile uses functional presets only.
3. **Nothing flows back automatically.** Updates go to customers; no usage tracking or error report sends client data out.
4. **Support never opens client records.**

## Why: the HIPAA question

Under HIPAA, a company that receives, stores or transmits patient information for a health-care provider is a *business associate*, with legal obligations. Encrypting the data isn't enough. U.S. HHS guidance on cloud computing:

> "If a CSP stores only encrypted ePHI and does not have a decryption key, is it a HIPAA business associate? Yes … even if it does not hold a decryption key and therefore cannot view the information."
>
> HHS, *Guidance on HIPAA & Cloud Computing* (hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing)

So the protection comes from patient information **never reaching AccessPath's systems**, not from locking it once it's there.

## Open questions for a lawyer (before the first health-care customer)

- Do functional numbers under a random code count as de-identified under HIPAA's de-identification standard, so a hosted engine could process them?
- Can a home's floor plan identify a person, and so need the same protection?
- Does running only on the customer's machine keep AccessPath out of business-associate status, including for support and updates?
- Does an account holding a name next to "requires accessibility modifications" count as health data under state laws that cover inferences (e.g. Washington's My Health My Data Act)?

This is general information, not legal advice.
