from server.mcp_server import mcp


@mcp.tool(description="Check that FitGen is reachable. Returns a short spoken confirmation.")
def ping() -> str:
    return "FitGen is up and ready to coach."
