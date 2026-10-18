"""
AI Resume & Job Match Analyzer - the window (tkinter).
All the thinking happens in analyzer.py. Run this file:  python app.py
"""

# ============================================================
# IMPORTS
# ============================================================
import csv
import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from analyzer import (
    COLOR_GREEN,
    COLOR_ORANGE,
    COLOR_RED,
    HAS_REPORTLAB,
    HISTORY_FILE,
    SAMPLE_JOB,
    SAMPLE_RESUME,
    add_history_entry,
    analysis_history,
    build_category_figure,
    build_report,
    build_report_sections,
    describe_change,
    find_previous_run,
    find_skill_positions,
    format_breakdown,
    format_categories,
    format_plan,
    format_skills,
    format_tips,
    get_learning_links,
    job_title_from_text,
    make_job_key,
    make_signature,
    rank_jobs,
    read_file,
    run_analysis,
    save_history,
    write_docx_report,
    write_pdf_report,
)

# Optional: only needed for the "Skills Chart" button.
try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


# ============================================================
# WINDOW CONSTANTS
# ============================================================
COLOR_BG = "#F3F6FA"
COLOR_DARK = "#173B67"
HIGHLIGHT_MATCHED = "#C9EBD3"   # light green background in the text boxes
HIGHLIGHT_MISSING = "#F6CFCF"   # light red background in the job box

REPORT_EXTENSIONS = {"PDF Document": ".pdf", "Word Document": ".docx",
                     "Text Report": ".txt"}

MAX_COMPARE_JOBS = 20          # most jobs allowed in "Compare Jobs"
MAX_PLAN_ITEMS_ON_SCREEN = 5   # the full plan always goes into the report

FILE_TYPES = [
    ("Supported Files", "*.pdf *.txt *.docx"),
    ("PDF Files", "*.pdf"),
    ("Text Files", "*.txt"),
    ("Word Documents", "*.docx"),
    ("All Files", "*.*"),
]

last_result = None      # the most recent analysis, used by "Learning Links"


# ============================================================
# 1. UI HELPER FUNCTIONS
# ============================================================
def make_button(parent, text, command, style="primary"):
    """Create a button. style: primary, dark, light, green."""
    styles = {
        "dark":    dict(bg=COLOR_DARK, fg="white", font=("Arial", 10, "bold")),
        "light":   dict(bg="#E1EAF5", fg=COLOR_DARK, font=("Arial", 10),
                        relief="flat", cursor="hand2"),
        "green":   dict(bg=COLOR_GREEN, fg="white", font=("Arial", 10, "bold")),
        "primary": dict(bg="#2463A6", fg="white", font=("Arial", 11, "bold"),
                        activebackground="#174B82", activeforeground="white",
                        relief="flat", cursor="hand2"),
    }
    button = tk.Button(parent, text=text, command=command,
                       padx=14, pady=6, **styles[style])
    button.pack(side="left", padx=5)
    return button


def run_in_background(work, on_done):
    """Run work() in a separate thread so the window never freezes.
    When it finishes, on_done(result, error) is called in the UI thread."""
    results = queue.Queue()

    def target():
        try:
            results.put((work(), None))
        except Exception as error:          # reported back to the UI thread
            results.put((None, error))

    threading.Thread(target=target, daemon=True).start()

    def poll():
        try:
            result, error = results.get_nowait()
        except queue.Empty:
            root.after(80, poll)            # not done yet, check again soon
            return
        on_done(result, error)

    poll()


def clear_highlights(widget):
    widget.tag_remove("matched", "1.0", tk.END)
    widget.tag_remove("missing", "1.0", tk.END)


def highlight_skills(widget, skill_names, tag):
    """Colour every mention of the given skills inside a text box."""
    content = widget.get("1.0", "end-1c")
    for start, end in find_skill_positions(content, skill_names):
        widget.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")


def highlight_result(result):
    """Green = skill you have, red = skill the job wants that you lack."""
    clear_highlights(resume_text)
    clear_highlights(job_text)
    highlight_skills(resume_text, result["matched_skills"], "matched")
    highlight_skills(job_text, result["matched_skills"], "matched")
    highlight_skills(job_text, result["missing_skills"], "missing")


def on_text_edit(event):
    """Typing makes old highlights wrong, so remove them."""
    if event.char.isprintable() or event.keysym in ("BackSpace", "Delete"):
        clear_highlights(event.widget)


def load_file_into(text_widget, label_widget, title, label_prefix, what):
    """Shared by both upload buttons: pick a file, read it (in the
    background, so big PDFs don't freeze the window), then show it."""
    file_path = filedialog.askopenfilename(title=title, filetypes=FILE_TYPES)
    if not file_path:
        return

    file_name = os.path.basename(file_path)
    old_label = label_widget.cget("text")
    label_widget.config(text=f"Reading {file_name} ...")

    def finish(content, error):
        if isinstance(error, ValueError):       # FileReadError: readable message
            label_widget.config(text=old_label)
            messagebox.showwarning("Cannot Read File", str(error))
            return
        if error is not None:
            label_widget.config(text=old_label)
            messagebox.showerror("File Error",
                                 f"Could not read the {what}:\n{error}")
            return
        if not content.strip():
            label_widget.config(text=old_label)
            messagebox.showwarning(
                "Unreadable File",
                f"No readable text was found in this {what}.\n\n"
                "The file may be scanned or image-based.\n"
                "Try a text-based PDF, DOCX, or TXT file.",
            )
            return

        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", content)
        label_widget.config(text=f"{label_prefix}: {file_name}")

    run_in_background(lambda: read_file(file_path), finish)


def upload_resume():
    load_file_into(resume_text, resume_file_label,
                   "Select Your Resume", "Selected Resume", "resume")


def upload_job_description():
    load_file_into(job_text, job_file_label,
                   "Select Job Description", "Selected Job Description",
                   "job description")


def load_sample():
    resume_text.delete("1.0", tk.END)
    resume_text.insert("1.0", SAMPLE_RESUME)
    job_text.delete("1.0", tk.END)
    job_text.insert("1.0", SAMPLE_JOB)


def clear_results():
    global last_result
    last_result = None
    score_label.config(text="Overall Match Score: 0.00%")
    status_label.config(text="Status: Waiting for analysis", fg="#555555")
    summary_label.config(text="Skills Matched: 0 | Skills Missing: 0")
    progress_fill.place_forget()
    category_label.config(text="By Category: None")
    matched_label.config(text="Matched Skills: None")
    missing_label.config(text="Missing Skills: None")
    recommendation_label.config(text="Learning Plan: None")
    tips_label.config(text="Resume Tips: None")
    breakdown_label.config(text="Score Breakdown: Not calculated")
    explanation_label.config(text="Why this score: Not calculated")
    progress_label.config(text="Progress: Not calculated")


def clear_resume():
    resume_text.delete("1.0", tk.END)
    resume_file_label.config(text="No resume file selected")
    clear_results()


def clear_job():
    job_text.delete("1.0", tk.END)
    job_file_label.config(text="No job description file selected")
    clear_results()


def get_inputs():
    """Read both text boxes. Return (resume, job) or None if invalid."""
    resume = resume_text.get("1.0", tk.END).strip()
    job = job_text.get("1.0", tk.END).strip()

    if not resume:
        messagebox.showwarning("Missing Resume", "Please enter your resume.")
        return None
    if not job:
        messagebox.showwarning("Missing Job Description",
                               "Please enter the job description.")
        return None
    return resume, job


def show_result(result):
    """Display an analysis result dictionary in the results panel."""
    pct = result["final_score"]

    score_label.config(text=f"Overall Match Score: {pct:.2f}%")
    status_label.config(text=f"Status: {result['status_text']}",
                        fg=result["status_color"])
    summary_label.config(
        text=f"Skills Matched: {len(result['matched_skills'])} | "
             f"Skills Missing: {len(result['missing_skills'])}"
    )
    breakdown_label.config(text=format_breakdown(result))
    explanation_label.config(text="Why this score: " + result["explanation"])

    # relwidth is a fraction of the track, so it resizes with the window.
    progress_fill.config(bg=result["status_color"])
    progress_fill.place(x=0, y=0, relwidth=pct / 100, relheight=1)

    preferred = result["preferred_skills"]
    category_label.config(
        text="By Category: " + format_categories(result["categories"])
    )
    matched_label.config(
        text="Matched Skills: "
             + (format_skills(result["matched_skills"], preferred) or "None")
    )
    missing_label.config(
        text="Missing Skills: "
             + (format_skills(result["missing_skills"], preferred) or "None")
    )

    recommendation_label.config(
        text="Learning Plan (most important first):\n"
             + format_plan(result, MAX_PLAN_ITEMS_ON_SCREEN)
    )
    tips_label.config(text="Resume Tips:\n" + format_tips(result))

    results_canvas.yview_moveto(0)   # start at the top of the results


def analyze_resume():
    inputs = get_inputs()
    if inputs is None:
        return
    resume, job = inputs

    analyze_button.config(state="disabled", text="Analyzing...")

    def finish(result, error):
        global last_result
        analyze_button.config(state="normal", text="Analyze Resume")

        if error is not None:
            messagebox.showerror("Analysis Error",
                                 f"Something went wrong:\n{error}")
            return

        if not result["required_skills"]:
            messagebox.showwarning(
                "No Skills Found",
                "No recognized skills were found in the job description.",
            )
            return

        show_result(result)
        highlight_result(result)
        last_result = result

        signature = make_signature(resume, job)
        job_key = make_job_key(job)

        # Progress: compare with your last run of this same job
        previous = find_previous_run(analysis_history, job_key, signature)
        if previous:
            progress_label.config(
                text="Progress: " + describe_change(
                    result["final_score"], result["matched_skills"], previous))
        else:
            progress_label.config(
                text="Progress: first run for this job. Improve your resume "
                     "and analyze again to track your progress.")

        # Skip history if this exact resume + job pair was already analyzed.
        if any(item["signature"] == signature for item in analysis_history):
            return

        save_error = add_history_entry({
            "signature": signature,
            "job_key": job_key,
            "job_title": job_title_from_text(job),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "final_score": round(result["final_score"], 2),
            "skill_score": round(result["skill_score"], 2),
            "text_score": round(result["text_score"], 2),
            "matched_skills": result["matched_skills"].copy(),
            "missing_skills": result["missing_skills"].copy(),
        })
        if save_error is not None:
            messagebox.showwarning(
                "History Not Saved",
                f"The analysis worked, but history could not be saved:\n{save_error}")

    run_in_background(lambda: run_analysis(resume, job), finish)


def show_skills_chart():
    """Open a window with a matched-vs-missing chart per category."""
    if last_result is None:
        messagebox.showinfo("No Analysis Yet",
                            "Click 'Analyze Resume' first, then open the chart.")
        return
    if not HAS_MATPLOTLIB:
        messagebox.showinfo(
            "Chart Unavailable",
            "The chart needs matplotlib. Install it with:\n\n"
            "pip install matplotlib\n\nthen restart the app.",
        )
        return

    window = tk.Toplevel(root)
    window.title("Skills Chart")
    window.geometry("740x450")
    figure = build_category_figure(last_result["categories"],
                                   last_result["final_score"])
    canvas = FigureCanvasTkAgg(figure, master=window)
    canvas.draw()
    canvas.get_tk_widget().pack(fill="both", expand=True)


def show_compare_jobs():
    """Window that ranks the resume in the main window against many jobs."""
    if not resume_text.get("1.0", tk.END).strip():
        messagebox.showwarning(
            "Missing Resume",
            "Enter or upload your resume in the main window first.")
        return

    window = tk.Toplevel(root)
    window.title("Compare Resume Against Several Jobs")
    window.geometry("920x640")
    window.minsize(760, 520)
    window.configure(bg=COLOR_BG)

    jobs = []     # [{"name": ..., "text": ...}] in the order they were added
    ranked = []   # filled after "Rank Jobs"; sorted best match first

    tk.Label(window, text="Compare Your Resume Against Several Jobs",
             font=("Arial", 15, "bold"), bg=COLOR_BG, fg=COLOR_DARK
             ).pack(pady=(12, 2))
    summary_label_cmp = tk.Label(window, text="No jobs added yet.",
                                 font=("Arial", 10), bg=COLOR_BG, fg="#555555")
    summary_label_cmp.pack(pady=(0, 8))

    # ---- buttons
    row1 = tk.Frame(window, bg=COLOR_BG)
    row1.pack(pady=(0, 4))
    row2 = tk.Frame(window, bg=COLOR_BG)
    row2.pack(pady=(0, 8))

    # ---- results table
    style = ttk.Style(window)
    style.configure("Treeview", rowheight=26, font=("Arial", 10))
    style.configure("Treeview.Heading", font=("Arial", 10, "bold"))

    table_frame = tk.Frame(window, bg=COLOR_BG)
    table_frame.pack(fill="x", padx=12)
    columns = ("rank", "job", "overall", "skills", "text", "matched")
    tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                        height=8, selectmode="browse")
    for name, title, width, anchor in [
        ("rank", "#", 40, "center"),
        ("job", "Job", 330, "w"),
        ("overall", "Overall", 80, "center"),
        ("skills", "Skill Match", 90, "center"),
        ("text", "Text", 70, "center"),
        ("matched", "Skills Matched", 120, "center"),
    ]:
        tree.heading(name, text=title)
        tree.column(name, width=width, anchor=anchor, stretch=(name == "job"))
    tree.tag_configure("good", foreground=COLOR_GREEN)
    tree.tag_configure("ok", foreground=COLOR_ORANGE)
    tree.tag_configure("low", foreground=COLOR_RED)
    tree.tag_configure("none", foreground="#888888")
    table_scroll = tk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=table_scroll.set)
    table_scroll.pack(side="right", fill="y")
    tree.pack(side="left", fill="x", expand=True)

    # ---- details box
    tk.Label(window, text="Details of the selected job",
             font=("Arial", 10, "bold"), bg=COLOR_BG, fg=COLOR_DARK,
             anchor="w").pack(fill="x", padx=14, pady=(10, 2))
    details = tk.Text(window, wrap="word", font=("Arial", 10), height=10,
                      padx=10, pady=8, bg="white", state="disabled")
    details.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def set_details(text):
        details.config(state="normal")
        details.delete("1.0", tk.END)
        details.insert("1.0", text)
        details.config(state="disabled")

    def selected_job_index():
        """Index into `jobs` of the selected row, or None."""
        selection = tree.selection()
        if not selection:
            return None
        position = int(selection[0])
        return ranked[position]["job_index"] if ranked else position

    def refresh_job_list():
        """Show the plain list of jobs (any old ranking is thrown away)."""
        ranked.clear()
        tree.delete(*tree.get_children())
        for index, job in enumerate(jobs):
            tree.insert("", "end", iid=str(index),
                        values=("-", job["name"], "-", "-", "-", "-"))
        summary_label_cmp.config(
            text=f"{len(jobs)} job(s) added. Click 'Rank Jobs' to compare."
            if jobs else "No jobs added yet.")
        set_details("Add jobs with the buttons above, then click 'Rank Jobs'.")

    def add_jobs(new_jobs):
        room = MAX_COMPARE_JOBS - len(jobs)
        if len(new_jobs) > room:
            messagebox.showinfo(
                "Job Limit",
                f"You can compare up to {MAX_COMPARE_JOBS} jobs at once. "
                f"Only the first {max(room, 0)} new job(s) were added.",
                parent=window)
            new_jobs = new_jobs[:max(room, 0)]
        jobs.extend(new_jobs)
        refresh_job_list()

    def add_pasted_job():
        dialog = tk.Toplevel(window)
        dialog.title("Paste Job Description")
        dialog.geometry("560x420")
        dialog.configure(bg=COLOR_BG)
        dialog.transient(window)

        tk.Label(dialog, text="Paste one job description below:",
                 font=("Arial", 11, "bold"), bg=COLOR_BG, fg=COLOR_DARK
                 ).pack(pady=(12, 4))
        box = tk.Text(dialog, wrap="word", font=("Arial", 10), padx=8, pady=8)
        box.pack(fill="both", expand=True, padx=12)

        def confirm():
            text = box.get("1.0", tk.END).strip()
            if not text:
                messagebox.showwarning("Empty", "Please paste a job description.",
                                       parent=dialog)
                return
            add_jobs([{"name": job_title_from_text(text), "text": text}])
            dialog.destroy()

        buttons = tk.Frame(dialog, bg=COLOR_BG)
        buttons.pack(pady=10)
        make_button(buttons, "Add This Job", confirm, "primary")
        make_button(buttons, "Cancel", dialog.destroy, "light")

    def add_job_files():
        paths = filedialog.askopenfilenames(
            title="Select Job Descriptions (you can pick several)",
            filetypes=FILE_TYPES, parent=window)
        if not paths:
            return

        def work():
            loaded, problems = [], []
            for path in paths:
                name = os.path.basename(path)
                try:
                    text = read_file(path)
                    if text.strip():
                        loaded.append({"name": name, "text": text})
                    else:
                        problems.append(f"{name}: no readable text")
                except Exception as error:
                    problems.append(f"{name}: {error}")
            return loaded, problems

        def done(result, error):
            if not window.winfo_exists():
                return
            if error is not None:
                messagebox.showerror("File Error", str(error), parent=window)
                return
            loaded, problems = result
            add_jobs(loaded)
            if problems:
                messagebox.showwarning("Some Files Were Skipped",
                                       "\n".join(problems), parent=window)

        run_in_background(work, done)

    def remove_selected():
        index = selected_job_index()
        if index is None:
            messagebox.showinfo("Nothing Selected",
                                "Click a job in the table first.", parent=window)
            return
        del jobs[index]
        refresh_job_list()

    def clear_all():
        jobs.clear()
        refresh_job_list()

    def show_ranked():
        tree.delete(*tree.get_children())
        for position, item in enumerate(ranked):
            result = item["result"]
            if not item["recognized"]:
                tree.insert("", "end", iid=str(position), tags=("none",),
                            values=("-", item["name"], "no skills found",
                                    "-", "-", "-"))
                continue
            score = result["final_score"]
            tag = "good" if score >= 80 else "ok" if score >= 60 else "low"
            total = len(result["matched_skills"]) + len(result["missing_skills"])
            tree.insert("", "end", iid=str(position), tags=(tag,), values=(
                position + 1, item["name"], f"{score:.1f}%",
                f"{result['skill_score']:.1f}%", f"{result['text_score']:.1f}%",
                f"{len(result['matched_skills'])} of {total}"))

        best = next((i for i in ranked if i["recognized"]), None)
        if best:
            summary_label_cmp.config(
                text=f"Best match: {best['name']} "
                     f"({best['result']['final_score']:.1f}%)   |   "
                     f"{len(ranked)} job(s) compared")
        else:
            summary_label_cmp.config(
                text="No recognized skills were found in any of the jobs.")
        set_details("Click a row to see its details.")

    def on_select(event):
        selection = tree.selection()
        if not selection:
            return
        if not ranked:
            set_details("Click 'Rank Jobs' to see the match details.")
            return

        item = ranked[int(selection[0])]
        if not item["recognized"]:
            set_details(f"{item['name']}\n\nNo recognized skills were found in "
                        "this job description, so it can't be scored. "
                        "Check that it lists skills (see skills.json).")
            return

        result = item["result"]
        preferred = result["preferred_skills"]
        plan = "\n".join(result["learning_plan"][:3]) or "Nothing missing."
        set_details(
            f"{item['name']}\n"
            f"Overall {result['final_score']:.1f}%  -  {result['status_text']}\n"
            f"{format_breakdown(result)}\n\n"
            f"Why: {result['explanation']}\n\n"
            f"Matched: {format_skills(result['matched_skills'], preferred) or 'None'}\n"
            f"Missing (most important first): "
            f"{format_skills(result['missing_skills'], preferred) or 'None'}\n\n"
            f"First things to learn:\n{plan}")

    tree.bind("<<TreeviewSelect>>", on_select)

    def rank():
        if not jobs:
            messagebox.showinfo("No Jobs", "Add at least one job first.",
                                parent=window)
            return
        resume = resume_text.get("1.0", tk.END).strip()
        if not resume:
            messagebox.showwarning("Missing Resume",
                                   "The resume in the main window is empty.",
                                   parent=window)
            return

        rank_button.config(state="disabled", text="Ranking...")
        snapshot = [dict(job) for job in jobs]

        def done(result, error):
            if not window.winfo_exists():
                return
            rank_button.config(state="normal", text="Rank Jobs")
            if error is not None:
                messagebox.showerror("Ranking Error", str(error), parent=window)
                return
            ranked[:] = result
            show_ranked()

        run_in_background(lambda: rank_jobs(resume, snapshot), done)

    def use_selected():
        index = selected_job_index()
        if index is None:
            messagebox.showinfo("Nothing Selected",
                                "Click a job in the table first.", parent=window)
            return
        job = jobs[index]
        job_text.delete("1.0", tk.END)
        job_text.insert("1.0", job["text"])
        job_file_label.config(text=f"Job from comparison: {job['name']}")
        root.lift()
        analyze_resume()

    def export_ranking():
        if not ranked:
            messagebox.showinfo("Nothing To Export",
                                "Click 'Rank Jobs' first.", parent=window)
            return
        file_path = filedialog.asksaveasfilename(
            parent=window, defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")], title="Save Job Ranking")
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["Rank", "Job", "Overall Score (%)",
                                 "Skill Match (%)", "Text Similarity (%)",
                                 "Matched Skills", "Missing Skills"])
                for position, item in enumerate(ranked, start=1):
                    result = item["result"]
                    if not item["recognized"]:
                        writer.writerow(["-", item["name"], "no skills found",
                                         "", "", "", ""])
                        continue
                    writer.writerow([
                        position, item["name"],
                        round(result["final_score"], 2),
                        round(result["skill_score"], 2),
                        round(result["text_score"], 2),
                        ", ".join(result["matched_skills"]),
                        ", ".join(result["missing_skills"]),
                    ])
            messagebox.showinfo("Export Successful", "Ranking saved.",
                                parent=window)
        except OSError as error:
            messagebox.showerror("Export Failed", str(error), parent=window)

    make_button(row1, "Add Job (paste)", add_pasted_job, "dark")
    make_button(row1, "Add Job Files", add_job_files, "dark")
    make_button(row1, "Remove Selected", remove_selected, "light")
    make_button(row1, "Clear All", clear_all, "light")
    rank_button = make_button(row2, "Rank Jobs", rank, "primary")
    make_button(row2, "Use Selected in Main Window", use_selected, "dark")
    make_button(row2, "Export Ranking", export_ranking, "green")

    refresh_job_list()


def show_learning_links():
    """Open a window with clickable learning links for each missing skill."""
    if last_result is None:
        messagebox.showinfo("No Analysis Yet",
                            "Click 'Analyze Resume' first, then open the links.")
        return
    missing = last_result["missing_skills"]
    if not missing:
        messagebox.showinfo("Nothing To Learn",
                            "You already have every recognized skill from the job.")
        return

    window = tk.Toplevel(root)
    window.title("Learning Links")
    window.geometry("760x520")
    window.configure(bg=COLOR_BG)

    tk.Label(window, text="Learning Links for Your Missing Skills",
             font=("Arial", 15, "bold"), bg=COLOR_BG, fg=COLOR_DARK
             ).pack(pady=(12, 2))
    tk.Label(window, text="Click a blue link to open it in your browser.",
             font=("Arial", 10), bg=COLOR_BG, fg="#555555").pack(pady=(0, 8))

    frame = tk.Frame(window, bg=COLOR_BG)
    frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")
    box = tk.Text(frame, wrap="word", font=("Arial", 11), padx=12, pady=10,
                  yscrollcommand=scrollbar.set, cursor="arrow", bg="white")
    box.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=box.yview)

    box.tag_config("heading", font=("Arial", 11, "bold"),
                   foreground=COLOR_DARK, spacing1=12, spacing3=2)

    link_count = 0
    for skill, plan_line in zip(missing, last_result["learning_plan"]):
        box.insert("end", plan_line + "\n", "heading")
        links = get_learning_links(skill)
        if not links:
            box.insert("end", "    (No links: show this skill through your experience.)\n")
        for label, url in links:
            link_count += 1
            tag = f"link{link_count}"
            box.insert("end", "    \u2022 ")
            box.insert("end", label, tag)
            box.insert("end", "\n")
            box.tag_config(tag, foreground="#1A5FB4", underline=True)
            box.tag_bind(tag, "<Button-1>", lambda e, u=url: webbrowser.open(u))
            box.tag_bind(tag, "<Enter>", lambda e: box.config(cursor="hand2"))
            box.tag_bind(tag, "<Leave>", lambda e: box.config(cursor="arrow"))

    box.config(state="disabled")


def show_analysis_history():
    window = tk.Toplevel(root)
    window.title("Analysis History")
    window.geometry("720x520")
    window.configure(bg=COLOR_BG)

    tk.Label(window, text="Previous Resume Analyses",
             font=("Arial", 16, "bold"), bg=COLOR_BG, fg=COLOR_DARK
             ).pack(pady=(10, 0))
    tk.Label(window, text=f"Saved on this computer: {HISTORY_FILE}",
             font=("Arial", 8), bg=COLOR_BG, fg="#777777", wraplength=680
             ).pack(pady=(0, 6))

    history_text = tk.Text(window, wrap="word", font=("Arial", 10),
                           width=75, height=18, padx=8, pady=6)
    history_text.pack(fill="both", expand=True, padx=10, pady=(4, 0))

    def clear_history():
        if not analysis_history:
            return
        if not messagebox.askyesno(
                "Clear History",
                "Delete all saved analyses? This cannot be undone.",
                parent=window):
            return
        analysis_history.clear()
        try:
            save_history([], HISTORY_FILE)
        except OSError as error:
            messagebox.showerror("Error", f"Could not update the file:\n{error}",
                                 parent=window)
        window.destroy()

    buttons = tk.Frame(window, bg=COLOR_BG)
    buttons.pack(pady=10)
    make_button(buttons, "Export to CSV", export_history_csv, "green")
    make_button(buttons, "Clear History", clear_history, "light")

    if not analysis_history:
        history_text.insert("end", "No analysis history available.")
    else:
        # Newest first
        for index in range(len(analysis_history) - 1, -1, -1):
            item = analysis_history[index]
            previous = find_previous_run(analysis_history[:index],
                                         item.get("job_key"), item["signature"])
            if previous:
                change = describe_change(item["final_score"],
                                         item.get("matched_skills", []), previous)
            else:
                change = "First run for this job."
            history_text.insert(
                "end",
                f"Analysis {index + 1}  ({item['time']})\n"
                f"Job: {item.get('job_title', 'Unknown')}\n"
                f"Overall Score: {item['final_score']}%  "
                f"(Skills {item['skill_score']}% | Text {item['text_score']}%)\n"
                f"Progress: {change}\n"
                f"Matched Skills: {', '.join(item['matched_skills']) or 'None'}\n"
                f"Missing Skills: {', '.join(item['missing_skills']) or 'None'}\n"
                f"{'-' * 60}\n",
            )
    history_text.config(state="disabled")


def export_history_csv():
    if not analysis_history:
        messagebox.showinfo(
            "No History",
            "Please analyze at least one resume before exporting history.",
        )
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv")],
        title="Save Analysis History",
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["Analysis Number", "Date & Time", "Job",
                             "Overall Score (%)", "Skill Match (%)",
                             "Text Similarity (%)", "Matched Skills",
                             "Missing Skills"])
            for number, item in enumerate(analysis_history, start=1):
                writer.writerow([
                    number,
                    item["time"],
                    item.get("job_title", ""),
                    item["final_score"],
                    item["skill_score"],
                    item["text_score"],
                    ", ".join(item["matched_skills"]),
                    ", ".join(item["missing_skills"]),
                ])
        messagebox.showinfo("Export Successful",
                            "Analysis history has been saved successfully.")
    except OSError as error:
        messagebox.showerror("Export Failed",
                             f"Could not save the file:\n{error}")


def download_report():
    inputs = get_inputs()
    if inputs is None:
        return
    resume, job = inputs

    # Fresh analysis from the CURRENT text, so the report is never stale.
    result = run_analysis(resume, job)

    if not result["required_skills"]:
        messagebox.showwarning(
            "No Skills Found",
            "No recognized skills were found in the job description.",
        )
        return

    type_choice = tk.StringVar(value="PDF Document")
    file_path = filedialog.asksaveasfilename(
        title="Save Resume Analysis Report",
        filetypes=[("PDF Document", "*.pdf"), ("Word Document", "*.docx"),
                   ("Text Report", "*.txt")],
        initialfile="Resume_Analysis_Report",
        typevariable=type_choice,
    )
    if not file_path:
        return

    extension = os.path.splitext(file_path)[1].lower()
    if extension not in (".pdf", ".docx", ".txt"):
        extension = REPORT_EXTENSIONS.get(type_choice.get(), ".pdf")
        file_path += extension

    if extension == ".pdf" and not HAS_REPORTLAB:
        messagebox.showinfo(
            "PDF Unavailable",
            "Saving a PDF needs reportlab. Install it with:\n\n"
            "pip install reportlab\n\nthen restart the app. "
            "You can also save as Word or Text for now.",
        )
        return

    try:
        sections = build_report_sections(result)
        if extension == ".pdf":
            write_pdf_report(sections, file_path)
        elif extension == ".docx":
            write_docx_report(sections, file_path)
        else:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(build_report(result))
        messagebox.showinfo("Report Saved",
                            f"Your report was saved successfully:\n{file_path}")
    except Exception as error:
        messagebox.showerror("Save Error",
                             f"Could not save the report:\n{error}")


# ============================================================
# 2. BUILD THE WINDOW
# ============================================================
root = tk.Tk()
root.title("AI Resume & Job Match Analyzer")
root.geometry("1000x840")
root.minsize(800, 600)
root.configure(bg=COLOR_BG)

# ---- Header ----
header = tk.Frame(root, bg=COLOR_DARK, height=110)
header.pack(fill="x")

tk.Label(header, text="AI Resume & Job Match Analyzer",
         font=("Arial", 23, "bold"), bg=COLOR_DARK, fg="white"
         ).pack(pady=(20, 5))
tk.Label(header, text="Analyze your resume against a job description",
         font=("Arial", 11), bg=COLOR_DARK, fg="#DCE8F5"
         ).pack(pady=(0, 15))

# ---- Two input panels ----
content = tk.Frame(root, bg=COLOR_BG)
content.columnconfigure(0, weight=1, uniform="columns")
content.columnconfigure(1, weight=1, uniform="columns")
content.rowconfigure(0, weight=1)


def make_input_panel(column, title, empty_label, padx):
    """Build one panel (frame + text box + file label). Returns (text, label)."""
    frame = tk.LabelFrame(content, text=f"  {title}  ",
                          font=("Arial", 12, "bold"), bg="white",
                          fg=COLOR_DARK, padx=10, pady=10)
    frame.grid(row=0, column=column, sticky="nsew", padx=padx)

    text = tk.Text(frame, height=8, width=35, font=("Arial", 11),
                   wrap="word", relief="flat", bg="#F8FAFD", fg="#202B3C",
                   padx=10, pady=10)
    text.pack(fill="both", expand=True)

    # Highlight colours used after an analysis
    text.tag_config("matched", background=HIGHLIGHT_MATCHED)
    text.tag_config("missing", background=HIGHLIGHT_MISSING)
    text.bind("<Key>", on_text_edit)
    text.bind("<<Paste>>", lambda e: clear_highlights(e.widget))
    text.bind("<<Cut>>", lambda e: clear_highlights(e.widget))

    label = tk.Label(frame, text=empty_label, font=("Arial", 9),
                     bg="white", fg="#555555", anchor="w", wraplength=400)
    label.pack(fill="x", pady=(5, 0))
    return text, label


resume_text, resume_file_label = make_input_panel(
    0, "Your Resume", "No resume file selected", (0, 10))
job_text, job_file_label = make_input_panel(
    1, "Job Description", "No job description file selected", (10, 0))

# Legend: explains the highlight colours shown after an analysis
legend = tk.Frame(content, bg=COLOR_BG)
legend.grid(row=1, column=0, columnspan=2, pady=(8, 0))
for color, meaning in [(HIGHLIGHT_MATCHED, "skill you have"),
                       (HIGHLIGHT_MISSING, "skill the job asks for that you are missing")]:
    tk.Label(legend, text="    ", bg=color, relief="solid", bd=1).pack(side="left")
    tk.Label(legend, text=f" {meaning}", font=("Arial", 9), bg=COLOR_BG,
             fg="#444444").pack(side="left", padx=(0, 18))

# ---- Buttons ----
button_frame = tk.Frame(root, bg=COLOR_BG)

# Row 1: getting data in
input_row = tk.Frame(button_frame, bg=COLOR_BG)
input_row.pack(pady=(0, 6))
make_button(input_row, "Upload Resume", upload_resume, "dark")
make_button(input_row, "Upload Job Description", upload_job_description, "dark")
make_button(input_row, "Load Sample", load_sample, "light")
make_button(input_row, "Clear Resume", clear_resume, "light")
make_button(input_row, "Clear Job", clear_job, "light")

# Row 2: analyzing and looking at the results
action_row = tk.Frame(button_frame, bg=COLOR_BG)
action_row.pack(pady=(0, 6))
analyze_button = make_button(action_row, "Analyze Resume", analyze_resume, "primary")
make_button(action_row, "Learning Links", show_learning_links, "dark")
make_button(action_row, "Skills Chart", show_skills_chart, "dark")

# Row 3: more tools
more_row = tk.Frame(button_frame, bg=COLOR_BG)
more_row.pack()
make_button(more_row, "Compare Jobs", show_compare_jobs, "dark")
make_button(more_row, "View History", show_analysis_history, "dark")
make_button(more_row, "Download Report", download_report, "dark")

# ---- Results panel (scrollable, so nothing is ever cut off) ----
results_frame = tk.LabelFrame(root, text=" Resume Analysis Results ",
                              font=("Arial", 12, "bold"), bg="white",
                              fg=COLOR_DARK, padx=10, pady=8)

results_canvas = tk.Canvas(results_frame, bg="white", height=270,
                           highlightthickness=0)
results_scrollbar = tk.Scrollbar(results_frame, orient="vertical",
                                 command=results_canvas.yview)
results_canvas.configure(yscrollcommand=results_scrollbar.set)
results_scrollbar.pack(side="right", fill="y")
results_canvas.pack(side="left", fill="both", expand=True)

# All result widgets live in this inner frame, inside the canvas.
results_inner = tk.Frame(results_canvas, bg="white")
results_window = results_canvas.create_window((0, 0), window=results_inner,
                                              anchor="nw")

result_labels = []   # kept so their wrap width can follow the window width


def make_result_label(text, font, fg, **pack_options):
    label = tk.Label(results_inner, text=text, font=font, bg="white", fg=fg,
                     wraplength=900, justify="left")
    label.pack(anchor="w", **pack_options)
    result_labels.append(label)
    return label


def on_inner_resize(event):
    results_canvas.configure(scrollregion=results_canvas.bbox("all"))


def on_canvas_resize(event):
    results_canvas.itemconfig(results_window, width=event.width)
    for label in result_labels:
        label.config(wraplength=max(event.width - 40, 200))


results_inner.bind("<Configure>", on_inner_resize)
results_canvas.bind("<Configure>", on_canvas_resize)


def on_mousewheel(event):
    if event.num == 4:            # Linux scroll up
        results_canvas.yview_scroll(-1, "units")
    elif event.num == 5:          # Linux scroll down
        results_canvas.yview_scroll(1, "units")
    else:                         # Windows / macOS
        results_canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")


def enable_scroll(event):
    results_canvas.bind_all("<MouseWheel>", on_mousewheel)
    results_canvas.bind_all("<Button-4>", on_mousewheel)
    results_canvas.bind_all("<Button-5>", on_mousewheel)


def disable_scroll(event):
    results_canvas.unbind_all("<MouseWheel>")
    results_canvas.unbind_all("<Button-4>")
    results_canvas.unbind_all("<Button-5>")


# The wheel only scrolls results while the mouse is over this panel,
# so it doesn't interfere with the resume / job text boxes.
results_frame.bind("<Enter>", enable_scroll)
results_frame.bind("<Leave>", disable_scroll)


score_label = make_result_label("Match Score: Not Analyzed",
                                ("Arial", 16, "bold"), COLOR_DARK, pady=5)
status_label = make_result_label("Status: Not Analyzed",
                                 ("Arial", 12, "bold"), "#555555", pady=4)
summary_label = make_result_label("Skills Matched: 0 | Skills Missing: 0",
                                  ("Arial", 11), "#333333", pady=4)
breakdown_label = make_result_label("Score Breakdown: Not calculated",
                                    ("Arial", 11), COLOR_DARK, pady=4)

# Progress bar (background track + coloured fill)
progress_background = tk.Frame(results_inner, bg="#D9E1EA", height=18)
progress_background.pack(fill="x", pady=8)
progress_background.pack_propagate(False)
progress_fill = tk.Frame(progress_background, bg="#2878C8", width=0)
progress_fill.place(x=0, y=0, relheight=1)

explanation_label = make_result_label("Why this score: Not calculated",
                                      ("Arial", 11, "italic"), "#333333", pady=4)
progress_label = make_result_label("Progress: Not calculated",
                                   ("Arial", 11, "italic"), "#1A5FB4", pady=4)
category_label = make_result_label("By Category: None",
                                   ("Arial", 11), COLOR_DARK, pady=4)
matched_label = make_result_label("Matched Skills: None",
                                  ("Arial", 11), "green", pady=5)
missing_label = make_result_label("Missing Skills: None",
                                  ("Arial", 11), "#C0392B", pady=5)
recommendation_label = make_result_label("Learning Plan: None",
                                         ("Arial", 11), COLOR_DARK, pady=8)
tips_label = make_result_label("Resume Tips: None",
                               ("Arial", 11), "#7A4B00", pady=8)

# ---- Layout ----
# Results and buttons are packed to the bottom FIRST, so they always get
# their space. The input panels take whatever room is left over.
results_frame.pack(side="bottom", fill="x", padx=20, pady=(0, 15))
button_frame.pack(side="bottom", pady=(0, 10))
content.pack(fill="both", expand=True, padx=20, pady=(15, 10))

# ============================================================
# 3. START THE APP
# ============================================================
root.mainloop()
