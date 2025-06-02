# UI Component Guide

Glimpser's templates use reusable Jinja macros to keep the interface consistent.
The `components.html` file defines common elements such as confirmation modals.

## Confirmation Modal

Use the `confirm_modal` macro when asking the user to verify an action:

```
{% from 'components.html' import confirm_modal %}
{{ confirm_modal('delete') }}
```

The macro renders a modal with `delete-modal`, `delete-close` and related IDs so
JavaScript can attach behavior consistently.

### Parameters
- **name** – base identifier for generated element IDs.
- **message** – text displayed inside the modal.
- **confirm** – label for the confirm button.
- **cancel** – label for the cancel button.

Including this component ensures all dialogs share the same markup and style.
