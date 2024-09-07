import os
import json
import yaml
import shutil
import asyncio
import argparse
import subprocess
import webbrowser
from hypercorn.config import Config
from quart import Quart, render_template, send_file, send_from_directory
from hypercorn.asyncio import serve as hypercorn_serve
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import markdown

class Mirage:
    def __init__(self):
        # Commands
        self.commands = [
            "init",
            "build",
            "serve",
            "deploy"
        ]
        self.serving = False
        self.navigation = None
        self.environment = None
        self.source = os.getcwd()

        # Default configuration
        self.read_config()

        # Argument parser
        parser = argparse.ArgumentParser(description="🏖 mirage is a static site generator in Python")
        parser.add_argument('command', type=str, help='Command to run', choices=self.commands)

        # Parse the arguments
        args = parser.parse_args()

        # Run the command
        match args.command:
            case "init":
                self.init()
            case "build":
                self.build()
            case "serve":
                self.serve()
            case "deploy":
                self.deploy()

    def get_url_for(self, filepath):
        # Get the URL for the given path
        if not self.serving and "baseurl" in self.config:
            paths = []
            paths.extend(list(filter(None, self.config["baseurl"].split("/"))))
            paths.extend(list(filter(None, filepath.split("/"))))
            return "/" + "/".join(paths)

        return filepath

    def read_config(self):
        # Read the configuration file
        with open("_config.yml") as f:
            self.config = yaml.safe_load(f)

        # Set the source path
        if "source" in self.config:
            self.source = self.config["source"]

        self.environment = Environment(loader=FileSystemLoader((os.path.join(self.source, "templates"))))
        self.environment.filters["url_for"] = self.get_url_for

    def init(self):
        # Create a new directory structure
        print("Creating a new site...")

    def build(self):
        # Remove the site directory if it exists
        shutil.rmtree("site", ignore_errors=True)

        # Steps for the building process
        # 1. Create a target directory for the build
        os.makedirs("site", exist_ok=True)

        # 2. Copy the static files to the target directory
        shutil.copytree(
            os.path.join(self.source, "static"),
            os.path.join("site", "static"),
            dirs_exist_ok=True)

        # Get navigation
        site_path = os.path.join(self.source, "site")
        self.navigation = self.get_navigation_for_folder(self.source, build=True)

        # Walk and render the files
        self.walk_dir(self.source)

    def walk_dir(self, directory):
        # Create directory in the build directory
        for file in os.listdir(directory):
            filepath = os.path.join(directory, file)
            rel_path = os.path.relpath(filepath, self.source)

            # Check if the file is excluded
            if file in self.config["exclude"]:
                continue

            # Check if the file is a directory
            if os.path.isdir(filepath):
                # Create the directory
                os.makedirs(os.path.join("site", rel_path), exist_ok=True)
                # Walk the directory
                self.walk_dir(filepath)
                continue

            # Render the file
            html = self.render_file(filepath)
            # Render the file
            with open(os.path.join("site", rel_path.replace(".md", ".html")), "w") as f:
                f.write(html)

    def serve(self):
        # Set the serving flag
        self.serving = True
        # Working dir
        working_dir = os.path.join(os.getcwd(), self.source)

        # Serve the application with quart
        app = Quart(__name__, template_folder=os.path.join(working_dir, "templates"), static_folder=os.path.join(working_dir, "static"))
        app.config["TEMPLATES_AUTO_RELOAD"] = True

        @app.before_request
        async def before_request():
            self.navigation = self.get_navigation_for_folder(self.source)

        # Catch all routes
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        async def catch_all(path):
            filepath = os.path.join(self.source, path)
            if not path:
                filepath = os.path.join(self.source, "index.md")
            return self.render_file(filepath)

        config = Config()
        config.use_reloader = True
        config.bind = [self.config["bind"]]
        asyncio.run(hypercorn_serve(app, config))

    def deploy(self):
        # Run a series of commands to deploy the site
        print("Deploying the site...")
        self.build()
        os.chdir("site")
        subprocess.run(["git", "init"])
        subprocess.run(["git", "add", "."])
        subprocess.run(["git", "commit", "-m", "Deploy"])
        subprocess.run(["git", "remote", "add", "origin", self.config["deploy"]])
        subprocess.run(["git", "push", "--force", "origin", "main:gh-pages"])
        os.chdir("..")
        print("Site deployed successfully!")

    def render_for_serve(self, file) -> str:
        # Get navigation
        navigation = self.get_navigation_for_folder(self.source)

        # Check if the file is a markdown file
        if not file.endswith(".md"):
            template = self.environment.get_template("static.html")
            html = template.render(url=file, navigation=navigation)
            return html

        # Read the file
        with open(os.path.join(self.source, file), "r", encoding="utf-8") as f:
            content = f.read()

        # Render the page with the default layout
        if not content.startswith("---"):
            html = markdown(content)
            template = self.environment.get_template(f"default.html")
            html = template.render(content=html, navigation=navigation)
            return html

        # Render the page with the given layout
        front_matter = {}
        front_matter, content = content.split("---")[1:]

        # Parse the front matter
        front_matter = yaml.safe_load(front_matter.strip())

        # Render the content
        html = markdown(content)

        # Render the page with the layout
        if "layout" in front_matter:
            layout = front_matter["layout"]
            template = self.environment.get_template(f"{layout}.html")
            html = template.render(content=html, navigation=navigation)
            return html

        return html

    def render_file(self, filepath) -> str:
        # Check if the file is a markdown file
        if not filepath.endswith(".md"):
            template = self.environment.get_template("static.html")
            html = template.render(url=filepath, navigation=self.navigation)
            return html

        # Read the file
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Render the page with the default layout
        if not content.startswith("---"):
            html = markdown(content)
            template = self.environment.get_template(f"default.html")
            html = template.render(content=html, navigation=self.navigation)
            return html

        # Render the page with the given layout
        front_matter = {}
        front_matter, content = content.split("---")[1:]

        # Parse the front matter
        front_matter = yaml.safe_load(front_matter.strip())

        # Render the content
        html = markdown(content)

        # Render the page with the layout
        layout = "default"
        if "layout" in front_matter:
            layout = front_matter["layout"]

        # Return markdown.html
        template = self.environment.get_template("markdown.html")
        html = template.render(content=html, navigation=self.navigation, **front_matter)
        return html

        # template = self.environment.get_template(f"{layout}.html")
        # html = template.render(content=html, navigation=self.navigation)
        # return html

    def get_navigation_for_folder(self, directory, build=False):
        navigation = {
            "type": "directory",
            "name": os.path.basename(directory),
            "files": []
        }

        # Check directory type
        if navigation["name"] == "javadoc":
            javadoc_path = os.path.join(directory, "index.html")
            navigation["type"] = "javadoc"
            navigation["url"] = f"/{os.path.relpath(javadoc_path, self.source)}"
            return navigation

        # Get the files in the directory
        files = os.listdir(directory)
        excluded_files = self.config["exclude"]
        files = [f for f in files if f not in excluded_files]
        files = sorted(files, key=lambda x: (os.path.isdir(os.path.join(directory, x)), x))

        # Sort the files, files first, directories next
        for file in files:
            # Directory
            if os.path.isdir(os.path.join(directory, file)):
                sub_navigation = self.get_navigation_for_folder(os.path.join(directory, file))
                navigation["files"].append(sub_navigation)
                continue

            # File
            path = os.path.join(directory, file)
            filename = os.path.basename(path)
            rel_path = os.path.relpath(path, self.source)

            # Check serving flag
            if not self.serving:
                filepath, _ = os.path.splitext(path)
                rel_path = os.path.relpath(filepath, self.source)

            # Get filename without extension
            navigation["files"].append({
                "type": "file",
                "name":filename,
                "url": f"/{rel_path}"
            })

        return navigation