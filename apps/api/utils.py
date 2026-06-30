from rest_framework.views import exception_handler
from rest_framework.response import Response


def api_response(data=None, message="", errors=None, status=200, success=True):
    payload = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=status)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        errors = response.data
        message = ""
        if isinstance(errors, dict):
            if "detail" in errors:
                message = str(errors.pop("detail"))
            if not message:
                for k, v in errors.items():
                    if isinstance(v, list) and v:
                        message = str(v[0])
                        break
                    if v:
                        message = str(v)
                        break
            if not message:
                message = str(getattr(exc, "detail", "حدث خطأ"))
        elif isinstance(errors, list):
            message = str(errors[0]) if errors else "حدث خطأ"
            errors = {"non_field_errors": errors}
        else:
            message = str(errors)
            errors = {"detail": str(errors)}

        response.data = {
            "success": False,
            "message": message,
            "data": None,
            "errors": errors,
        }
    return response
