"""Setup help the assistant can read, so it works the same in every AI client.

Not every client can open files from this repository, so the connection steps, the
notebook cells and the example training scripts are available as tools.
"""

from .. import doctor, guide


def register(mcp):
    @mcp.tool()
    def setup_guide(platform: str = "") -> str:
        """How to connect a place to run on: "colab", "kaggle", "huggingface" or "space".

        With no platform it reports what is already set up and what is missing. For Colab
        and Kaggle the answer includes the exact notebook cell to give to the user.
        Use this whenever the user asks how to connect, or a tool says nothing is connected.
        """
        if not platform.strip():
            return (doctor.endpoints() + "\n\nFor step-by-step instructions call setup_guide with one of: "
                    + ", ".join(guide.PLATFORMS) + ".")
        return guide.guide(platform)

    @mcp.tool()
    def example_script(name: str = "") -> str:
        """Return a ready-made training script to pass to launch_training / hf_job_launch.

        With no name it lists the examples (LLM LoRA fine-tune, RL PPO, CV CNN). Each
        script's header says how to launch it and which settings it accepts.
        """
        names = guide.list_assets("examples")
        if not name.strip():
            return "Examples: " + ", ".join(names) + ". Call example_script(name) for the code."
        name = name.strip()
        if not name.endswith(".py"):
            name += ".py"
        if name not in names:
            return f"No example named {name!r}. Available: {', '.join(names)}."
        return guide.read_asset("examples", name)
