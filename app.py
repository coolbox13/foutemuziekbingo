import uvicorn
from app.fastapi_app import create_app
from app.socket_handler import sio_app
import socketio

# Create FastAPI app
fastapi_app = create_app()

# Create combined app with Socket.IO
app = socketio.ASGIApp(sio_app, other_asgi_app=fastapi_app)

# Print all registered routes for debugging
for route in fastapi_app.routes:
    if hasattr(route, 'methods'):
        print(f"{route.methods}: {route.path}")
    else:
        print(f"Route: {route}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=1313, reload=False)