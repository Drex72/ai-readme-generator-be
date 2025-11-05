#!/usr/bin/env python3

import click
import os
import sys
from pathlib import Path
from rich.console import Console
from rich.progress import track
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .services.local_repository_service import LocalRepositoryService
from .services.gemini_service import GeminiService
from .utils.config_manager import ConfigManager
from .types import DEFAULT_SECTIONS

console = Console()
config_manager = ConfigManager()

@click.group()
@click.version_option(version="1.0.0")
def cli():
    """AI-powered README generator for local projects."""
    pass

@cli.command()
@click.option('--path', '-p', default='.', help='Project path')
@click.option('--output', '-o', default='README.md', help='Output file name')
@click.option('--sections', '-s', multiple=True, help='Sections to include')
@click.option('--no-interactive', is_flag=True, help='Skip interactive prompts')
@click.option('--overwrite', is_flag=True, help='Overwrite existing README without confirmation')
def generate(path, output, sections, no_interactive, overwrite):
    """Generate a README for the current project."""
    try:
        _generate_readme(path, output, sections, not no_interactive, overwrite)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

@cli.command()
@click.option('--set-api-key', help='Set Gemini API key')
@click.option('--get-api-key', is_flag=True, help='Show current API key (masked)')
@click.option('--set-sections', multiple=True, help='Set default sections')
@click.option('--get-sections', is_flag=True, help='Show default sections')
def config(set_api_key, get_api_key, set_sections, get_sections):
    """Configure the CLI tool."""
    try:
        if set_api_key:
            config_manager.set_gemini_api_key(set_api_key)
            console.print("[green]✅ Gemini API key saved[/green]")
            return

        if get_api_key:
            api_key = config_manager.get_gemini_api_key()
            if api_key:
                masked = api_key[:8] + '*' * (len(api_key) - 8)
                console.print(f"[blue]Current API key: {masked}[/blue]")
            else:
                console.print("[yellow]No API key configured[/yellow]")
            return

        if set_sections:
            valid_section_ids = [s['id'] for s in DEFAULT_SECTIONS]
            valid_sections = [s for s in set_sections if s in valid_section_ids]

            if not valid_sections:
                console.print("[red]No valid sections provided[/red]")
                return

            config_manager.set_default_sections(valid_sections)
            console.print(f"[green]✅ Default sections set: {', '.join(valid_sections)}[/green]")
            return

        if get_sections:
            sections = config_manager.get_default_sections()
            console.print(f"[blue]Default sections: {', '.join(sections)}[/blue]")
            return

        # Interactive configuration
        _interactive_config()

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

@cli.command()
def sections():
    """List available README sections."""
    table = Table(title="Available README Sections")
    table.add_column("ID", style="green")
    table.add_column("Name", style="blue")
    table.add_column("Description", style="dim")

    for section in DEFAULT_SECTIONS:
        table.add_row(section['id'], section['name'], section['description'])

    console.print(table)

@cli.command()
@click.option('--file', '-f', default='README.md', help='README file to refine')
@click.option('--output', '-o', help='Output file name')
def refine(file, output):
    """Refine an existing README with feedback."""
    try:
        _refine_readme(file, output)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

def _generate_readme(project_path, output_file, sections, interactive, overwrite):
    """Generate README implementation."""
    # Check for API key
    api_key = config_manager.get_gemini_api_key()
    if not api_key:
        console.print("[yellow]No Gemini API key found. Please set one first:[/yellow]")
        console.print("[cyan]ai-readme config --set-api-key YOUR_API_KEY[/cyan]")
        console.print("[dim]Get your API key from: https://makersuite.google.com/app/apikey[/dim]")
        return

    project_path = Path(project_path).resolve()

    # Check if path exists
    if not project_path.exists():
        raise ValueError(f"Path does not exist: {project_path}")

    # Check for existing README
    output_path = project_path / output_file
    if output_path.exists() and not overwrite:
        if interactive:
            if not Confirm.ask(f"{output_file} already exists. Overwrite?"):
                console.print("[yellow]Generation cancelled.[/yellow]")
                return
        else:
            console.print(f"[yellow]{output_file} already exists. Use --overwrite to overwrite.[/yellow]")
            return

    console.print(f"[blue]🔍 Analyzing project at: {project_path}[/blue]")

    # Analyze repository
    with console.status("Analyzing repository structure..."):
        repo_service = LocalRepositoryService(str(project_path))
        repo_info = repo_service.analyze_repository()

    console.print(f"Analyzed [green]{repo_info['name']}[/green] ([blue]{repo_info.get('language', 'Unknown')}[/blue])")

    # Select sections
    if sections:
        # Use provided sections
        valid_section_ids = [s['id'] for s in DEFAULT_SECTIONS]
        sections_to_generate = [s for s in DEFAULT_SECTIONS if s['id'] in sections or s['name'].lower() in [sec.lower() for sec in sections]]
    elif interactive:
        # Interactive section selection
        sections_to_generate = _select_sections_interactive()
    else:
        # Use default sections
        default_section_ids = config_manager.get_default_sections()
        sections_to_generate = [s for s in DEFAULT_SECTIONS if s['id'] in default_section_ids]

    if not sections_to_generate:
        raise ValueError("No sections selected for generation")

    section_names = [s['name'] for s in sections_to_generate]
    console.print(f"[blue]📝 Generating README with sections: {', '.join(section_names)}[/blue]")

    # Generate README
    with console.status("Generating README with AI..."):
        gemini_service = GeminiService(api_key)
        result = gemini_service.generate_readme(repo_info, sections_to_generate)

    # Write to file
    output_path.write_text(result['content'], encoding='utf-8')

    console.print(f"[green]✅ README generated successfully![/green]")
    console.print(f"[green]📄 README saved to: {output_path}[/green]")
    console.print(f"[dim]   Sections generated: {', '.join(result['sections_generated'])}[/dim]")
    console.print(f"[dim]   Content length: {len(result['content'])} characters[/dim]")

def _select_sections_interactive():
    """Interactive section selection."""
    console.print("[blue]Select sections to include:[/blue]")

    selected_sections = []
    for section in DEFAULT_SECTIONS:
        default = section.get('required', False)
        if Confirm.ask(f"Include {section['name']}? ({section['description']})", default=default):
            selected_sections.append(section)

    return selected_sections

def _interactive_config():
    """Interactive configuration setup."""
    current_config = config_manager.load_config()

    # API Key configuration
    if not current_config.get('gemini_api_key'):
        api_key = Prompt.ask("Enter your Gemini API key", password=True)
        if api_key:
            config_manager.set_gemini_api_key(api_key)

    # Default sections configuration
    if not current_config.get('default_sections'):
        console.print("[blue]Select default sections:[/blue]")
        default_sections = []
        for section in DEFAULT_SECTIONS:
            if Confirm.ask(f"Include {section['name']} by default?", default=section.get('required', False)):
                default_sections.append(section['id'])

        if default_sections:
            config_manager.set_default_sections(default_sections)

    console.print("[green]✅ Configuration saved[/green]")

def _refine_readme(readme_file, output_file):
    """Refine README implementation."""
    # Check for API key
    api_key = config_manager.get_gemini_api_key()
    if not api_key:
        console.print("[yellow]No Gemini API key found. Please set one first:[/yellow]")
        console.print("[cyan]ai-readme config --set-api-key YOUR_API_KEY[/cyan]")
        return

    readme_path = Path(readme_file).resolve()

    if not readme_path.exists():
        raise ValueError(f"README file not found: {readme_path}")

    # Read existing README
    existing_content = readme_path.read_text(encoding='utf-8')

    # Get feedback from user
    feedback = Prompt.ask("What would you like to improve in the README?")

    if not feedback.strip():
        console.print("[yellow]No feedback provided.[/yellow]")
        return

    with console.status("Refining README with AI..."):
        gemini_service = GeminiService(api_key)
        refined_content = gemini_service.refine_readme(existing_content, feedback)

    # Determine output path
    output_path = Path(output_file).resolve() if output_file else readme_path

    # Write refined content
    output_path.write_text(refined_content, encoding='utf-8')

    console.print(f"[green]✅ README refined successfully![/green]")
    console.print(f"[green]📄 Refined README saved to: {output_path}[/green]")

def main():
    """Entry point for the CLI."""
    cli()

if __name__ == '__main__':
    main()