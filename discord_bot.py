import discord
import os
import json
import uuid
import re
from discord import app_commands
from discord.ui import View, Select, Button, Modal, TextInput

CONFIG_FILE = 'config.json'
METADATA_FILE = 'file_metadata.json'
UPLOAD_FOLDER = 'cdn_files'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'webm'}

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f: return json.load(f)
    except FileNotFoundError:
        print(f"[Bot] Error: {CONFIG_FILE} not found. Run the web app first.")
        exit()

def load_metadata():
    if not os.path.exists(METADATA_FILE): return {}
    try:
        with open(METADATA_FILE, 'r') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return {}

def save_metadata(data):
    with open(METADATA_FILE, 'w') as f: json.dump(data, f, indent=4)

config = load_config()
TOKEN = config.get('discord_bot_token')
BASE_URL = config.get('base_url')
AUTHORIZED_USER_IDS = set(config.get('authorized_user_ids', []))

if not TOKEN or not BASE_URL:
    print("[Bot] Error: 'discord_bot_token' or 'base_url' missing from config.")
    exit()

def is_authorized():
    return app_commands.check(lambda i: str(i.user.id) in AUTHORIZED_USER_IDS)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_filename(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '', name)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


class RenameModal(Modal, title='Rename File'):
    def __init__(self, parent_view: 'FileManagementView', original_filename: str):
        super().__init__()
        self.parent_view = parent_view
        self.original_filename = original_filename
        self.new_name_input = TextInput(
            label='New Filename (without extension)',
            placeholder='e.g., my-renamed-file',
            required=True
        )
        self.add_item(self.new_name_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_name_base = sanitize_filename(str(self.new_name_input.value).strip())
        if not new_name_base:
            await interaction.response.edit_message(content="Error: New name cannot be empty.", view=self.parent_view)
            return

        old_path = os.path.join(UPLOAD_FOLDER, self.original_filename)
        file_ext = os.path.splitext(self.original_filename)[1]
        new_filename = f"{new_name_base}{file_ext}"
        new_path = os.path.join(UPLOAD_FOLDER, new_filename)

        if os.path.exists(new_path):
            await interaction.response.edit_message(content=f"Error: A file named '{new_filename}' already exists.", view=self.parent_view)
            return
        
        try:
            os.rename(old_path, new_path)
            metadata = load_metadata()
            if self.original_filename in metadata:
                metadata[new_filename] = metadata.pop(self.original_filename)
                save_metadata(metadata)
            
            self.parent_view.query = None 
            self.parent_view.update_file_options()
            for item in self.parent_view.children: item.disabled = isinstance(item, Button)
            self.parent_view.select_file.disabled = not self.parent_view.select_file.options
            
            await interaction.response.edit_message(content=f"Success: Renamed to **{new_filename}**. Select a file.", view=self.parent_view)
        except Exception as e:
            await interaction.response.edit_message(content=f"An unexpected error occurred during rename: {e}", view=self.parent_view)



class SearchModal(Modal, title="Search for Files"):
    def __init__(self):
        super().__init__()
        self.query_input = TextInput(
            label="Search Query",
            placeholder="Leave blank to show all files.",
            required=False
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        query = str(self.query_input.value).strip() or None
        new_view = FileManagementView(query=query)
        await interaction.response.edit_message(content=new_view.message_content, view=new_view)



class ManageFileModal(Modal):
    def __init__(self, parent_view: 'FileManagementView', filename: str, mode: str):
        self.parent_view = parent_view
        self.filename = filename
        self.mode = mode
        
        title = f"Set {mode.capitalize()} for {filename}"
        super().__init__(title=title)

        self.input_field = TextInput(
            label=f"New {mode.capitalize()}",
            placeholder=f"Enter {mode} or leave blank to remove." if mode == "password" else "Enter a number (e.g., 10).",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        value = str(self.input_field.value)
        metadata = load_metadata()
        if self.filename not in metadata: metadata[self.filename] = {}

        if self.mode == 'password':
            if value: metadata[self.filename]['password'] = value
            elif 'password' in metadata[self.filename]: del metadata[self.filename]['password']
        elif self.mode == 'lock':
            if value and value.isdigit() and int(value) > 0:
                metadata[self.filename]['visit_limit'] = int(value)
                if 'visit_count' not in metadata[self.filename]: metadata[self.filename]['visit_count'] = 0
            else:
                if 'visit_limit' in metadata[self.filename]: del metadata[self.filename]['visit_limit']
                if 'visit_count' in metadata[self.filename]: del metadata[self.filename]['visit_count']
        
        save_metadata(metadata)
        await self.parent_view.update_message_after_action(interaction, self.filename)



class FileManagementView(View):
    def __init__(self, query: str = None):
        super().__init__(timeout=300)
        self.query = query
        self.message_content = "Select a file to get started."
        if self.query:
            self.message_content = f"Showing results for \"{self.query}\". Select a file."
        self.selected_file = None
        self.update_file_options()

    def update_file_options(self):
        self.select_file.options.clear()
        try:
            files = sorted([f for f in os.listdir(UPLOAD_FOLDER) if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))])
            if self.query:
                files = [f for f in files if self.query.lower() in f.lower()]

            if not files:
                self.select_file.disabled = True
                self.select_file.placeholder = "No files match your search." if self.query else "No files found."
            else:
                self.select_file.disabled = False
                self.select_file.placeholder = "Select a file to manage..."
                for filename in files[:25]:
                    self.select_file.append_option(discord.SelectOption(label=filename))
        except FileNotFoundError:
            self.select_file.disabled = True
            self.select_file.placeholder = "Error: CDN directory not found."

    async def update_message_after_action(self, interaction: discord.Interaction, filename: str):
        metadata = load_metadata()
        file_meta = metadata.get(filename, {})
        pwd_status = f"**Password:** {'Yes' if file_meta.get('password') else 'No'}"
        lock_status = "**Lock:** Not set"
        if file_meta.get('visit_limit') is not None:
            count = file_meta.get('visit_count', 0)
            limit = file_meta.get('visit_limit')
            lock_status = f"**Lock:** {count}/{limit} visits"

        self.message_content = f"Managing: **{filename}**\n\n{pwd_status}\n{lock_status}\n\nSelect an action."
        for item in self.children:
            if isinstance(item, Button): item.disabled = False 
        await interaction.response.edit_message(content=self.message_content, view=self)

    @discord.ui.select(row=0)
    async def select_file(self, interaction: discord.Interaction, select: Select):
        self.selected_file = select.values[0]
        await self.update_message_after_action(interaction, self.selected_file)

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.primary, emoji="✏️", row=1, disabled=True)
    async def button_rename(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RenameModal(self, self.selected_file))

    @discord.ui.button(label="Set Password", style=discord.ButtonStyle.secondary, emoji="🔑", row=1, disabled=True)
    async def button_set_password(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ManageFileModal(self, self.selected_file, 'password'))

    @discord.ui.button(label="Set Lock", style=discord.ButtonStyle.secondary, emoji="🔒", row=1, disabled=True)
    async def button_set_lock(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ManageFileModal(self, self.selected_file, 'lock'))

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️", row=2, disabled=True)
    async def button_delete(self, interaction: discord.Interaction, button: Button):
        file_path = os.path.join(UPLOAD_FOLDER, self.selected_file)
        if os.path.exists(file_path):
            os.remove(file_path)
            metadata = load_metadata()
            if self.selected_file in metadata:
                del metadata[self.selected_file]
                save_metadata(metadata)
            
            self.update_file_options()
            for item in self.children: item.disabled = isinstance(item, Button)
            self.select_file.disabled = not self.select_file.options
            self.message_content = f"Success: Deleted **{self.selected_file}**. Select a new file."
            await interaction.response.edit_message(content=self.message_content, view=self)
        else:
            await interaction.response.edit_message(content=f"Error: '{self.selected_file}' no longer exists.", view=None)

    @discord.ui.button(label="Get Link", style=discord.ButtonStyle.success, emoji="🔗", row=2, disabled=True)
    async def button_get_link(self, interaction: discord.Interaction, button: Button):
        metadata = load_metadata()
        file_meta = metadata.get(self.selected_file, {})
        base_link = f"{BASE_URL}/files/{self.selected_file}"
        
        if password := file_meta.get('password'):
            link = f"<{base_link}?password={password}>"
            self.message_content = f"Link for **{self.selected_file}** (includes password):\n\n{link}"
        else:
            link = f"<{base_link}>"
            self.message_content = f"Link for **{self.selected_file}**:\n\n{link}"
        await interaction.response.edit_message(content=self.message_content, view=None)

    @discord.ui.button(label="Rerun Search", style=discord.ButtonStyle.blurple, emoji="🔍", row=2)
    async def button_rerun_query(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(SearchModal())



@tree.command(name="upload", description="Upload a file to the CDN with optional protection.")
@discord.app_commands.user_install()
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    file="The file to upload.",
    custom_name="Optional custom name for the file (without extension).",
    password="Set a password to access the file.",
    visit_limit="Lock the file after this many visits."
)
@is_authorized()
async def upload_command(interaction: discord.Interaction, file: discord.Attachment, custom_name: str = None, password: str = None, visit_limit: int = None):
    
    if not allowed_file(file.filename):
        return await interaction.response.send_message("Error: This file type is not allowed.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    file_ext = os.path.splitext(file.filename)[1]
    new_filename = f"{sanitize_filename(custom_name) or uuid.uuid4().hex}{file_ext}"
    save_path = os.path.join(UPLOAD_FOLDER, new_filename)
    if os.path.exists(save_path):
        return await interaction.followup.send(f"Error: A file named '{new_filename}' already exists.", ephemeral=True)
    try:
        await file.save(save_path)
        metadata = load_metadata()
        metadata[new_filename] = {'visit_count': 0}
        if password: metadata[new_filename]['password'] = password
        if visit_limit and visit_limit > 0: metadata[new_filename]['visit_limit'] = visit_limit
        save_metadata(metadata)
        link = f"{BASE_URL}/files/{new_filename}"
        await interaction.followup.send(f"Success! File uploaded.\nYour link: {link}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"An error occurred during upload: {e}", ephemeral=True)

@tree.command(name="manage", description="Manage files in the CDN. Can be filtered with a query.")
@discord.app_commands.user_install()
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(query="An optional search term to filter the file list.")
@is_authorized()
async def manage_command(interaction: discord.Interaction, query: str = None):
    view = FileManagementView(query=query)
    await interaction.response.send_message(view.message_content, view=view, ephemeral=True)

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    
    content = "An unexpected error occurred."
    if isinstance(error, app_commands.CheckFailure):
        content = "You are not authorized to use this command."
    print(f"[Bot Error] User: {interaction.user.id}, Command: {interaction.command.name if interaction.command else 'Unknown'}, Error: {error}")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True)
        else:
            await interaction.response.send_message(content, ephemeral=True)
    except discord.errors.InteractionResponded:
        await interaction.followup.send(content, ephemeral=True)
    except Exception as e:
        print(f"[Bot Error] Failed to send error message: {e}")

@client.event
async def on_ready():
    
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    await tree.sync()
    print(f"[Bot] Logged in as {client.user}")

client.run(TOKEN)