"""`manage.py mcp` — serve the chalani register over the Model Context Protocol."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from chalani.mcp_server import READ_TOOLS, SERVER_NAME, WRITE_TOOLS, build_server
from orgs.models import Membership, Organization


class Command(BaseCommand):
    help = (
        f"Run the '{SERVER_NAME}' MCP server over the chalani register. "
        "Read-only unless --allow-writes is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--org",
            help="Organization slug to serve. Optional when the database holds only one.",
        )
        parser.add_argument(
            "--allow-writes",
            action="store_true",
            help="Also expose the tools that change data (update, link, verify).",
        )
        parser.add_argument(
            "--transport",
            default="stdio",
            choices=["stdio", "streamable-http", "sse"],
            help="stdio (default) for a local client; streamable-http to serve over a port.",
        )
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8931)
        parser.add_argument(
            "--list-orgs",
            action="store_true",
            help="Print servable organizations and exit.",
        )
        parser.add_argument(
            "--list-tools", action="store_true", help="Print the tool surface and exit."
        )

    def handle(self, *args, **options):
        if options["list_orgs"]:
            for org in Organization.objects.all():
                members = Membership.objects.filter(organization=org).count()
                self.stdout.write(f"{org.slug}\t{org}\t({members} members)")
            return

        organization = self._resolve_org(options.get("org"))
        allow_writes = options["allow_writes"]

        if options["list_tools"]:
            self.stdout.write(f"MCP server '{SERVER_NAME}' — {organization}")
            for fn in READ_TOOLS:
                self.stdout.write(f"  {fn.__name__:22} read")
            self.stdout.write(f"  {'convert_date':22} read")
            for fn in WRITE_TOOLS:
                state = "write" if allow_writes else "write (disabled)"
                self.stdout.write(f"  {fn.__name__:22} {state}")
            return

        server = build_server(organization, allow_writes=allow_writes)
        transport = options["transport"]

        # stdout is the protocol channel on stdio — every human-readable line
        # has to go to stderr or it corrupts the stream.
        self.stderr.write(
            f"MCP server '{SERVER_NAME}' serving {organization} over {transport}"
            f"{' with writes enabled' if allow_writes else ' (read-only)'}"
        )
        if transport == "stdio":
            server.run("stdio")
        else:
            server.run(transport, host=options["host"], port=options["port"])

    @staticmethod
    def _resolve_org(slug: str | None) -> Organization:
        if slug:
            try:
                return Organization.objects.get(slug=slug)
            except Organization.DoesNotExist as exc:
                available = ", ".join(
                    Organization.objects.values_list("slug", flat=True)
                )
                raise CommandError(
                    f"no organization with slug '{slug}'. Available: {available or 'none'}"
                ) from exc
        organizations = list(Organization.objects.all()[:2])
        if not organizations:
            raise CommandError(
                "no organizations exist yet — run `manage.py seed_demo` first"
            )
        if len(organizations) > 1:
            raise CommandError(
                "several organizations exist — pick one with --org <slug> "
                "(see `manage.py mcp --list-orgs`)"
            )
        return organizations[0]
