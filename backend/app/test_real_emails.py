#!/usr/bin/env python3
"""
Gmail Real Email Testing Script

Interactive CLI tool to test the Gmail monitoring system with real emails.
Uses the Rich library for formatted console output.

Usage:
    python -m app.test_real_emails
"""
import asyncio
import sys
from datetime import datetime

# Handle missing rich gracefully
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: 'rich' library not installed. Using plain text output.")
    print("Install with: pip install rich")

from app.gmail_monitor import gmail_monitor
from app.gmail_service import gmail_service


def create_console():
    """Create console or fallback."""
    if RICH_AVAILABLE:
        return Console()
    return None


console = create_console()


def print_message(text: str, style: str = None):
    """Print with or without rich formatting."""
    if RICH_AVAILABLE and console:
        console.print(text, style=style)
    else:
        # Strip rich markup for plain output
        import re
        plain = re.sub(r'\[.*?\]', '', text)
        print(plain)


def show_instructions():
    """Print instructions for sending test emails."""
    instructions = """
[bold cyan]Gmail Testing Instructions[/bold cyan]

1. [yellow]Send an email to yourself:[/yellow]
   Subject: Discount Request - MedTech Corp
   Body: 
   Hi,
   Can we approve 18% discount for MedTech Corp?
   They have 3 SEV-1 incidents and are threatening churn.
   - John Sales

2. [yellow]Reply to your own email:[/yellow]
   Approved at 15%. 18% is too high given margin.
   - Jane Manager

3. [yellow]Wait 10-20 seconds[/yellow] for Gmail to sync

4. [yellow]Run this script again[/yellow] to find and ingest the email

[dim]Tip: Make sure the email subject contains 'discount' or 'approval' for detection[/dim]
"""
    if RICH_AVAILABLE and console:
        console.print(Panel(instructions, title="How to Test"))
    else:
        print_message(instructions)


async def search_and_display(query: str = "subject:(discount OR approval)") -> list:
    """Search Gmail and display results."""
    print_message("\n[bold]Searching Gmail for decision emails...[/bold]")
    
    messages = await gmail_monitor.search_decision_emails(query, max_results=10)
    
    if not messages:
        print_message("\n[yellow]No emails found matching the query.[/yellow]")
        print_message("[dim]Did you send test emails? Check the subject contains 'discount' or 'approval'[/dim]")
        return []
    
    print_message(f"\n[green]Found {len(messages)} emails![/green]\n")
    
    if RICH_AVAILABLE and console:
        # Rich table display
        table = Table(title="Gmail Decision Emails", show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Message ID", style="cyan", no_wrap=True)
        table.add_column("Subject", style="green", max_width=40)
        table.add_column("From", style="yellow", max_width=25)
        table.add_column("Date", style="dim")
        
        for i, msg in enumerate(messages, 1):
            msg_id = msg.get('id', '?')[:12] + "..."
            subject = (msg.get('subject', 'No Subject') or 'No Subject')[:40]
            sender = (msg.get('from', msg.get('sender', 'Unknown')) or 'Unknown')[:25]
            date = msg.get('date', 'Unknown')
            
            # Highlight if unprocessed
            if msg.get('id') not in gmail_monitor.processed_message_ids:
                table.add_row(str(i), msg_id, f"[bold]{subject}[/bold]", sender, date)
            else:
                table.add_row(str(i), f"[dim]{msg_id}[/dim]", f"[dim]{subject} ✓[/dim]", f"[dim]{sender}[/dim]", f"[dim]{date}[/dim]")
        
        console.print(table)
    else:
        # Plain text display
        print("-" * 80)
        for i, msg in enumerate(messages, 1):
            print(f"{i}. [{msg.get('id', '?')[:12]}...] {msg.get('subject', 'No Subject')}")
            print(f"   From: {msg.get('from', msg.get('sender', 'Unknown'))}")
            print(f"   Date: {msg.get('date', 'Unknown')}")
            print()
        print("-" * 80)
    
    return messages


async def ingest_and_show(message_id: str, customer_name: str):
    """Ingest an email and display results."""
    print_message(f"\n[bold]Ingesting message {message_id[:12]}...[/bold]")
    
    result = await gmail_monitor.ingest_email(
        message_id=message_id,
        customer_name=customer_name,
        auto_save=True
    )
    
    if result['success']:
        trace = result['trace']
        
        if RICH_AVAILABLE and console:
            console.print(f"\n[green]✅ Success![/green] Decision ID: [cyan]{result['decision_id']}[/cyan]")
            
            console.print(Panel(f"""
[bold]Request:[/bold]
  Customer: {trace.request.customer}
  Requested: {trace.request.requested_action}
  Requestor: {trace.request.requestor_email or 'Unknown'}
  Reason: {trace.request.reason or 'Not specified'}

[bold]Decision:[/bold]
  Outcome: {trace.decision.outcome.value}
  Final Action: {trace.decision.final_action}
  Approver: {trace.decision.decision_maker_email or 'Unknown'}
  Reasoning: {trace.decision.reasoning or 'Not specified'}

[bold]Context:[/bold]
  Evidence pieces: {len(trace.evidence)}
  Policy exceptions: {len(trace.exceptions)}
  Precedents found: {len(trace.precedents)}
""", title="Extracted Decision Trace"))
            
        else:
            print(f"\n✅ Success! Decision ID: {result['decision_id']}")
            print(f"\nRequest: {trace.request.requested_action}")
            print(f"Decision: {trace.decision.final_action} ({trace.decision.outcome.value})")
            print(f"Approver: {trace.decision.decision_maker_email}")
        
        print_message("\n[dim]Saved to Neo4j. Query with:[/dim]")
        print_message(f"[cyan]curl http://localhost:8000/decision/explain/{result['decision_id']}[/cyan]")
        
    else:
        print_message(f"\n[red]❌ Failed: {result.get('error', 'Unknown error')}[/red]")


async def interactive_mode(messages: list):
    """Interactive mode to select and ingest emails."""
    if not messages:
        return
    
    # Check for unprocessed messages
    unprocessed = [m for m in messages if m.get('id') not in gmail_monitor.processed_message_ids]
    
    if not unprocessed:
        print_message("\n[yellow]All found emails have already been processed.[/yellow]")
        print_message("[dim]Send new test emails or reset the monitor.[/dim]")
        return
    
    print_message(f"\n[bold]{len(unprocessed)} unprocessed email(s) available[/bold]")
    
    if RICH_AVAILABLE:
        choice = Prompt.ask(
            "Enter email number to ingest (or 'all' for batch, 'q' to quit)",
            default="1"
        )
    else:
        choice = input("Enter email number to ingest (or 'all' for batch, 'q' to quit) [1]: ").strip() or "1"
    
    if choice.lower() == 'q':
        return
    
    if choice.lower() == 'all':
        # Batch ingest
        print_message("\n[bold]Starting batch ingestion...[/bold]")
        result = await gmail_monitor.batch_ingest(
            query="subject:(discount OR approval)",
            max_results=len(unprocessed)
        )
        print_message(f"\n[green]Batch complete: {result['successful']} successful, {result['failed']} failed[/green]")
        return
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(messages):
            msg = messages[idx]
            
            # Extract customer name from subject
            subject = msg.get('subject', '')
            if ' - ' in subject:
                default_customer = subject.split(' - ')[-1].strip()
            else:
                default_customer = "Test Customer"
            
            if RICH_AVAILABLE:
                customer = Prompt.ask("Customer name", default=default_customer)
            else:
                customer = input(f"Customer name [{default_customer}]: ").strip() or default_customer
            
            await ingest_and_show(msg['id'], customer)
        else:
            print_message("[red]Invalid selection[/red]")
    except ValueError:
        print_message("[red]Invalid input - enter a number[/red]")


async def main():
    """Main CLI interface."""
    print_message("\n[bold magenta]═══════════════════════════════════════════[/bold magenta]")
    print_message("[bold magenta]  Context Graph - Gmail Real Email Tester  [/bold magenta]")
    print_message("[bold magenta]═══════════════════════════════════════════[/bold magenta]\n")
    
    # Check Gmail connection
    gmail_status = gmail_service.check_connection()
    if not gmail_status.get('connected'):
        print_message("[red]Gmail not connected![/red]")
        print_message(f"[yellow]Status: {gmail_status.get('message', 'Unknown')}[/yellow]")
        print_message("\n[dim]Make sure credentials.json exists and run OAuth flow first.[/dim]")
        return
    
    print_message("[green]Gmail connected ✓[/green]")
    
    # Show instructions
    show_instructions()
    
    # Search and display
    messages = await search_and_display()
    
    # Interactive selection
    await interactive_mode(messages)
    
    print_message("\n[dim]Done! Visit /docs to explore API endpoints.[/dim]\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(0)
