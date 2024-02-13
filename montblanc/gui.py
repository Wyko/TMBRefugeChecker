import tkinter as tk
from contextlib import suppress
from typing import Literal, Tuple

import customtkinter

from montblanc import logic
from montblanc.logic import Settings

customtkinter.set_appearance_mode("System")  # Modes: system (default), light, dark
customtkinter.set_default_color_theme("blue")  # Themes: blue (default), dark-blue, green


class MainApplication(customtkinter.CTk):
    def __init__(self, fg_color: str | Tuple[str, str] | None = None, **kwargs):
        super().__init__(fg_color, **kwargs)
        self.title("TMB Refuge Monitor")
        self.settings = Settings.load()

    def create_left_frame(self):
        left_frame = customtkinter.CTkFrame(self, width=300)
        left_frame.pack(side=tk.LEFT, fill="y", expand=False, anchor="w", padx=(0, 3), ipadx=10, ipady=10)

        label = customtkinter.CTkLabel(left_frame, text="TMB Refuge Monitor\nv0.1.0\n\n By: Wyko ter Haar")
        label.pack(pady=10)

        self.btn_plan = customtkinter.CTkButton(
            left_frame, text="Create Plan", command=lambda: self.open_tool("Create Plan")
        )
        self.btn_plan.pack(pady=4)

        self.btn_check = customtkinter.CTkButton(left_frame, text="Monitor Plan", command=self.quit)
        self.btn_check.pack(pady=4)

        self.btn_find = customtkinter.CTkButton(left_frame, text="Automatic Date Picker", command=self.quit)
        self.btn_find.pack(pady=4)

        self.btn_quit = customtkinter.CTkButton(left_frame, text="Quit", command=self.quit, fg_color="grey")
        self.btn_quit.pack(pady=30)

        return left_frame

    def open_tool(self, tool: str):
        with suppress(AttributeError):
            self.frm_main.destroy()

        if tool == "Create Plan":
            self.frm_main = CreatePlan(self, settings=self.settings)
        elif tool == "Monitor Plan":
            pass
        elif tool == "Automatic Date Picker":
            pass
        else:
            raise ValueError("Invalid tool")

        self.frm_main.pack(side=tk.RIGHT, fill="both", expand=True, anchor="e")

    def run(self):
        self.frm_left = self.create_left_frame()
        self.open_tool("Create Plan")
        self.minsize(700, 300)
        self.geometry()

        self.mainloop()


class CreatePlan(customtkinter.CTkFrame):
    def __init__(self, parent, settings: Settings, **kwargs):
        self.settings: Settings = settings
        super().__init__(master=parent, **kwargs)
        self.create_plan_picker()
        self.create_plan_frame()
        self.pack(fill="both", expand=True)

    def create_plan_picker(self):
        self.frm_picker = customtkinter.CTkFrame(self)
        self.frm_picker.pack(
            side=tk.TOP, fill="x", expand=False, anchor="w", padx=5, pady=(5, 2), ipadx=5, ipady=5
        )
        self.frm_picker.columnconfigure(0, weight=1)
        self.frm_picker.columnconfigure(1, weight=0)

        self.lst_plans = logic.load_recent_plans(self.settings.recent_plans)

        row = self.frm_picker.grid_size()[1]
        self.cbo_plan = customtkinter.CTkComboBox(self.frm_picker, values=[p for p in self.lst_plans])
        self.cbo_plan.set("Select Plan" if self.lst_plans else "No Plans Found")
        self.cbo_plan.grid(row=row + 1, column=0, padx=5, pady=5, sticky="ew")
        lbl_picker = customtkinter.CTkLabel(self.frm_picker, text="Select Existing Plan")
        lbl_picker.grid(row=row, column=0, padx=5)

        btn_create_new = customtkinter.CTkButton(self.frm_picker, text="New Plan", command=self.create_plan)
        btn_create_new.grid(row=row, column=1, padx=5, pady=5)

        btn_del_plan = customtkinter.CTkButton(
            self.frm_picker, text="Delete Plan", command=self.delete_plan, fg_color="grey"
        )
        btn_del_plan.grid(row=row + 1, column=1, padx=5, pady=5)

    def create_plan_frame(self):
        self.frm_plan = customtkinter.CTkFrame(self)
        self.frm_plan.pack(side=tk.BOTTOM, fill="both", expand=True, padx=5, pady=(2, 5))

        self.ent_plan_name = customtkinter.CTkEntry(self.frm_plan, placeholder_text="Plan Name")
        self.ent_plan_name.pack(pady=(10, 5), padx=5, anchor="nw", side="top", fill="x", expand=False)

        self.scr_refuges = customtkinter.CTkScrollableFrame(self.frm_plan)
        self.scr_refuges.pack(pady=5, padx=5, anchor="s", side="bottom", fill="both", expand=True)

        frm_rfg1 = RefugeFrame(self.scr_refuges, "Refuge 1")
        frm_rfg1.pack(pady=5, padx=5, anchor="w", side="top", fill="x", expand=False)

    def create_plan(self):
        pass

    def delete_plan(self):
        curr_plan = self.cbo_plan.get()
        if curr_plan == "Select Plan" or not curr_plan or curr_plan == "No Plans Found":
            return
        result = WarningDialog(
            self,
            title="Delete Plan",
            message=f"Are you sure you want to delete this plan?\n\n{curr_plan}",
        ).show()
        if result == "ok":
            pass


class RefugeFrame(customtkinter.CTkFrame):
    def __init__(self, parent, name: str, **kwargs):
        super().__init__(parent, **kwargs)
        self.name = name
        self.create_widgets()

    def create_widgets(self):
        lbl_name = customtkinter.CTkLabel(self, text=self.name)
        lbl_name.pack(pady=5, padx=5, anchor="w", side="top", fill="x", expand=False)

        self.ent_date = customtkinter.CTkEntry(self, placeholder_text="Date")
        self.ent_date.pack(pady=5, padx=5, anchor="w", side="top", fill="x", expand=False)

        self.ent_capacity = customtkinter.CTkEntry(self, placeholder_text="People Capacity Needed")
        self.ent_capacity.pack(pady=5, padx=5, anchor="w", side="top", fill="x", expand=False)

        self.ent_status = customtkinter.CTkEntry(self, placeholder_text="Status")
        self.ent_status.pack(pady=5, padx=5, anchor="w", side="top", fill="x", expand=False)

        self.ent_note = customtkinter.CTkEntry(self, placeholder_text="Note")
        self.ent_note.pack(pady=5, padx=5, anchor="w", side="top", fill="x", expand=False)


class WarningDialog(customtkinter.CTkToplevel):
    def __init__(self, parent, title: str, message: str, **kwargs):
        super().__init__(parent, **kwargs)
        self.message = message
        self.result: Literal["ok", "cancel"] = "cancel"
        self.create_widgets()

        self.attributes("-topmost", True)
        self.update()

        self.after_idle(lambda: self.focus_force())

    def create_widgets(self):
        lbl_message = customtkinter.CTkLabel(self, text=self.message)
        lbl_message.pack(pady=10)

        frm_buttons = customtkinter.CTkFrame(self)
        frm_buttons.pack(pady=10)

        btn_ok = customtkinter.CTkButton(frm_buttons, text="OK", command=self.ok)
        btn_ok.pack(pady=10, padx=10, side=tk.LEFT)

        btn_cancel = customtkinter.CTkButton(frm_buttons, text="Cancel", command=self.destroy)
        btn_cancel.pack(pady=10, padx=10, side=tk.LEFT)

    def ok(self):
        self.result = "ok"
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


if __name__ == "__main__":
    app = MainApplication()
    app.run()
