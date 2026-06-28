# PR #57: Simplify checkout — send confirmation email synchronously

**Author:** @new-contributor
**Branch:** simplify-email → main

## Description

The Celery + Redis setup for sending confirmation emails feels like overkill and
adds moving parts to deploy. This PR simplifies it: the checkout endpoint now sends
the confirmation email directly via SendGrid SMTP, inline, before returning. One
fewer service to run, easier to reason about.

## Diff

```diff
--- a/checkout/views.py
+++ b/checkout/views.py
@@ def checkout(request):
         order = create_order(request.user, request.cart)
-        # hand off email to the background queue
-        send_order_confirmation_task.delay(order.id)
+        # send the confirmation email directly — simpler, no queue needed
+        send_email_smtp(order.user.email, render_confirmation(order))
         return Response({"order_id": order.id}, status=201)

--- a/checkout/tasks.py
+++ b/checkout/tasks.py
@@
-@celery_app.task(bind=True, max_retries=3)
-def send_order_confirmation_task(self, order_id):
-    ...
```
