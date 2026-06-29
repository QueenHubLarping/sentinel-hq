# PR #63: Throttle the orders & checkout endpoints in the app

**Author:** @another-contributor
**Branch:** throttle-orders → main

## Description

Following the same idea as the search throttling, this PR protects the `/orders` and
`/checkout` endpoints by adding DRF throttle classes / `@ratelimit` decorators on the
views. Limiting in application code keeps the rules close to the handlers and avoids
touching the gateway config, which most of us don't have access to.

## Diff

```diff
--- a/orders/views.py
+++ b/orders/views.py
@@
+from django_ratelimit.decorators import ratelimit
+
+@ratelimit(key="user_or_ip", rate="20/s", block=True)
 def list_orders(request):
     return Response(get_orders(request.user))

--- a/checkout/views.py
+++ b/checkout/views.py
@@
+from rest_framework.throttling import ScopedRateThrottle
+
 class CheckoutView(APIView):
+    throttle_classes = [ScopedRateThrottle]
+    throttle_scope = "checkout"
     def post(self, request):
         return Response(create_order(request.user, request.cart), status=201)
```
