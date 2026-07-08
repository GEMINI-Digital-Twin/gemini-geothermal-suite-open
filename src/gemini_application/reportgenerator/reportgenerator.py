"""PDF report generation for well performance analysis and monitoring data."""

import io
import os
from datetime import datetime, timezone
from math import ceil, sqrt

import matplotlib
import matplotlib.dates as mdates
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
from matplotlib import rcParams
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

from gemini_application.application_abstract import ApplicationAbstract
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.well.pressure_drop import DPDT

matplotlib.use("Agg")


class ReportGenerator(ApplicationAbstract):
    """Class for generating reports.

    The class retrieves data from the database and generates a report in pdf format.
    """

    def __init__(self):
        """Initialize report generator."""
        super().__init__()
        self.plant_name = None
        self.project_path = None
        self.start_time = None
        self.end_time = None
        self.start_datestamp_title = None
        self.end_datestamp_title = None
        self.timestep = 3600  # Default value is 1 hour since usually values are given /h
        self.database_internal = None
        self.database_external = None
        self.pdf_buffer = None
        self.pdf_object = None
        self.author_name = None
        self.project_name = None
        self.number_days = None
        self.page_size = (11.69, 8.27)

        # Well pressure drop model
        self.well_DP = DPDT()
        self.well_DP.PVT = PVTConstantSTP()

    def init_parameters(self, **kwargs):
        """Initialize parameters."""
        for key, value in kwargs.items():
            setattr(self, key, value)

        start_dt = datetime.strptime(self.start_time, "%Y-%m-%d %H:%M:%S")
        self.start_datestamp_title = (
            f"{start_dt.month}/"
            f"{start_dt.day}/"
            f"{start_dt.year} "
            f"{start_dt.strftime('%H')}:{start_dt.strftime('%M')}"
        )

        end_dt = datetime.strptime(self.end_time, "%Y-%m-%d %H:%M:%S")
        self.end_datestamp_title = (
            f"{end_dt.month}/"
            f"{end_dt.day}/"
            f"{end_dt.year} "
            f"{end_dt.strftime('%H')}:{end_dt.strftime('%M')}"
        )

    def calculate(self):
        """Calculate report data."""
        # Class ReportGenerator does not require calculations
        pass

    def get_units(self, tagname):
        """Get units for given tagname."""
        tag = tagname.lower()
        unit_map = {
            "pressure": "[bar]",
            "temperature": "[°C]",
            "flow": "[m^3/h]",
            "frequency": "[Hz]",
            "current": "[A]",
            "power": "[kW]",
        }
        for key, unit in unit_map.items():
            if key in tag:
                return unit
        return "[-]"

    def _read_internal_series(self, tagname):
        """Read a time series from the internal database for the selected unit."""
        return self.plant.database.read_internal_database(
            self.unit.plant.name,
            self.unit.name,
            tagname,
            self.start_time,
            self.end_time,
            self.timestep,
        )

    def _unit_names_containing(self, needle):
        """Return unit names containing a substring."""
        return [unit.name for unit in self.plant.units if needle in unit.name]

    def get_data(self, tagname):
        """Get data for given tagname."""
        return self._read_internal_series(tagname)

    def initialize_pdf_object(self):
        """Initialize PDF object."""
        self.pdf_buffer = io.BytesIO()
        self.pdf_object = PdfPages(self.pdf_buffer)
        return

    def add_title_page(self):
        """Add title page to PDF."""
        title = f"{self.project_name} Report"
        date_str = datetime.now().strftime("%A, %B %dth %Y, %I:%M %p")
        author = self.author_name

        if not hasattr(self, "pdf_object") or self.pdf_object is None:
            raise ValueError(
                "PDF object is not initialized. " "Ensure self.pdf_object is properly set."
            )

        fig, ax = plt.subplots()
        ax.axis("off")  # Remove axes

        # Title: centered in the page
        ax.text(0.5, 0.5, title, fontsize=32, fontweight="bold", ha="center", va="center")

        # Author and Date: below the title, left aligned
        ax.text(0.1, 0.42, f"Date: {date_str}", fontsize=14, ha="left", va="top")
        ax.text(0.1, 0.38, f"Author: {author}", fontsize=14, ha="left", va="top")

        # Logo at top-right
        try:
            logo_img = mpimg.imread(".\\static\\images\\gemini_DDT_V1_300dpi.jpg")
            imagebox = OffsetImage(logo_img, zoom=0.2)
            ab = AnnotationBbox(imagebox, (0.95, 0.92), frameon=False, box_alignment=(1, 1))
            ax.add_artist(ab)
        except FileNotFoundError:
            # Placeholder if no logo image
            ax.text(0.95, 0.92, "[Logo Here]", fontsize=12, ha="right", va="top", style="italic")

        # Save to PDF
        width, height = 11.69, 8.27
        fig.set_size_inches(width, height)
        self.pdf_object.savefig(fig, bbox_inches="tight", pad_inches=0.5)
        plt.close(fig)

    def get_injection_wells(self):
        """Get injection wells data."""
        return self._unit_names_containing("injection_well")

    def get_production_wells(self):
        """Get production wells data."""
        return self._unit_names_containing("production_well")

    def get_esps(self):
        """Get ESP data."""
        return self._unit_names_containing("esp")

    def get_hexs(self):
        """Get HEX data."""
        return self._unit_names_containing("heat_exchanger")

    def add_timeseries_plot_to_pdf(self, data, timestamps, xlabel, ylabel, title):
        """Add timeseries plot to PDF."""
        plt.figure(figsize=(10, 5))
        dates = pd.to_datetime(timestamps, utc=True)
        plt.plot(dates, data, linestyle="-", color="b", label="Time Series")

        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
        plt.gcf().autofmt_xdate()

        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.title(title)
        plt.legend()
        plt.grid()

        self.pdf_object.savefig()
        plt.close()

    def add_X_Y_plot_to_pdf(self, x_data, y_data):
        """Add X-Y plot to PDF."""
        plt.figure(figsize=(11.69, 8.27))
        plt.plot(x_data, y_data, marker="o", linestyle="-", color="r", label="X-Y Plot")
        plt.xlabel("X Data")
        plt.ylabel("Y Data")
        plt.title("X-Y Plot")
        plt.legend()
        plt.grid()
        self.pdf_object.savefig()
        plt.close()

    def get_clean_list(self, value_list):
        """Get clean list from value list."""
        return [float(value) for value in value_list if self._is_float_like(value)]

    @staticmethod
    def _is_float_like(value):
        """Check whether a value can be converted to float."""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False

    def add_stats_plot(self, inj_wells, prod_wells):
        """Add statistics plot to PDF."""
        inj_well_tagnames = [
            "injectionwell_flow.measured",
            "injectionwell_wellhead_pressure.measured",
            "injectionwell_annulus_a_pressure.measured",
        ]
        prod_well_tagnames = [
            "productionwell_annulus_a_pressure.measured",
            "productionwell_annulus_b_pressure.measured",
        ]

        all_wells = inj_wells + prod_wells
        unit_tag_pairs = []

        for well_name in all_wells:
            if "injection" in well_name:
                unit_tag_pairs.append((well_name, inj_well_tagnames))
            elif "production" in well_name:
                unit_tag_pairs.append((well_name, prod_well_tagnames))

        num_units = len(unit_tag_pairs)
        max_tags_per_unit = max(len(tags) for _, tags in unit_tag_pairs)

        # Create subplots with constrained layout
        fig, axes = plt.subplots(
            num_units, max_tags_per_unit, sharex=False, constrained_layout=True
        )

        # Normalize axes to 2D array
        if num_units == 1:
            axes = [axes]
        if max_tags_per_unit == 1:
            axes = [[ax] for ax in axes]

        for row_idx, (well_name, tagnames) in enumerate(unit_tag_pairs):
            self.select_unit(well_name)

            for col_idx in range(max_tags_per_unit):
                ax = axes[row_idx][col_idx]

                if col_idx >= len(tagnames):
                    ax.axis("off")
                    continue

                tagname = tagnames[col_idx]
                value_list, datestamp_list = self.get_data(tagname)
                clean_list = self.get_clean_list(value_list)

                if not clean_list or not datestamp_list:
                    ax.set_title(f"{well_name}\n{tagname}\nNo Data")
                    ax.axis("off")
                    continue

                try:
                    dates = [datetime.fromisoformat(ts.replace("Z", "")) for ts in datestamp_list]
                    max_value = max(clean_list)
                    max_index = value_list.index(max_value)

                    # Plot data
                    ax.plot(dates, value_list, linestyle="-", color="blue", linewidth=1)
                    ax.scatter(dates[max_index], max_value, color="red", zorder=5)

                    # Max value overlay
                    ax.text(
                        0.5,
                        0.5,
                        f"{max_value:.2f}",
                        transform=ax.transAxes,
                        fontsize=26 if num_units > 3 else 32,
                        ha="center",
                        va="center",
                        weight="bold",
                        color="black",
                        zorder=10,
                    )

                    ax.set_title(f"{well_name}\n{tagname}", fontsize=9)
                    ax.grid(True)
                    ax.set_xticks([])
                    ax.set_xticklabels([])
                    ax.tick_params(axis="y", labelsize=8)
                    ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins="auto"))

                except Exception as e:
                    ax.set_title(f"Error: {tagname}")
                    ax.text(0.5, 0.5, str(e), transform=ax.transAxes, ha="center", va="center")
                    ax.axis("off")

        fig.suptitle(
            f"{self.project_name} — Max values during the period "
            f"{self.start_datestamp_title} - {self.end_datestamp_title}",
            fontsize=14,
            fontweight="bold",
        )

        fig.set_size_inches(11.69, 8.27)
        self.pdf_object.savefig(fig, bbox_inches="tight", pad_inches=0.3)
        plt.close(fig)

    def gather_stats(self, well_names, tagnames):
        """Gather statistics for wells."""
        stats_data = []
        for well_name in well_names:
            self.select_unit(well_name)
            for tagname in tagnames:
                value_list, datestamp_list = self.get_data(tagname)
                clean_list = self.get_clean_list(value_list)
                if not clean_list or not datestamp_list:
                    continue  # Skip empty data

                # Compute stats
                max_value = max(clean_list)
                min_value = min(clean_list)
                mean_value = np.mean(clean_list)
                std_value = np.std(clean_list)

                # Timestamp for max value
                try:
                    max_index = value_list.index(max_value)
                    max_timestamp = datestamp_list[max_index]
                    max_datetime = datetime.fromisoformat(max_timestamp.replace("Z", ""))
                    timestamp_str = max_datetime.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    timestamp_str = "N/A"

                stats_data.append(
                    [
                        well_name,
                        tagname,
                        f"{min_value:.2f}",
                        f"{max_value:.2f}",
                        f"{mean_value:.2f}",
                        f"{std_value:.2f}",
                        timestamp_str,
                    ]
                )
        return stats_data

    def add_injection_report(self, inj_wells, tagnames):
        """Add injection report to PDF."""
        num_wells = len(inj_wells)
        if num_wells == 0:
            return

        fig, axes = plt.subplots(num_wells, 1, sharex=True)
        if num_wells == 1:
            axes = [axes]  # Ensure iterable

        fig.suptitle("Injection wells report", fontsize=16, fontweight="bold")
        color_cycle = plt.cm.tab10.colors

        # Separate injectivity tagnames and others, preserving order
        injectivity_tags = [tn for tn in tagnames if "injectivity" in tn.lower()]
        other_tags = [tn for tn in tagnames if "injectivity" not in tn.lower()]

        for idx, (well_name, ax_left) in enumerate(zip(inj_wells, axes)):
            self.select_unit(well_name)

            tag_data = {}
            timestamps = None

            # Collect tag data
            for tagname in tagnames:
                value_list, datestamp_list = self.get_data(tagname)
                if not value_list or not datestamp_list:
                    continue
                try:
                    dates = [datetime.fromisoformat(ts.replace("Z", "")) for ts in datestamp_list]
                    if timestamps is None:
                        timestamps = dates
                    tag_data[tagname] = value_list
                except Exception as e:
                    print(f"Error processing tag '{tagname}' for well '{well_name}': {e}")

            if not tag_data or timestamps is None:
                ax_left.set_title(f"{well_name} (No data)")
                ax_left.axis("off")
                continue

            ax_list = [ax_left]
            color_idx = 0

            # Plot injectivity (left y-axis)
            for tagname in injectivity_tags:
                if tagname in tag_data:
                    label = f"{tagname} [-]"
                    ax_left.plot(
                        timestamps, tag_data[tagname], color=color_cycle[color_idx], label=label
                    )
                    ax_left.set_ylabel(label, color=color_cycle[color_idx])
                    ax_left.tick_params(axis="y", labelcolor=color_cycle[color_idx])
                    ax_left.yaxis.set_major_locator(ticker.MaxNLocator(nbins=5))
                    ax_left.grid(True, linestyle="--", alpha=0.4, axis="y")
                    # Add vertical gridlines
                    ax_left.grid(True, linestyle="--", alpha=0.4, axis="x")
                    color_idx += 1
                    break  # Only one injectivity on left axis
            else:
                # If no injectivity tag found, still add vertical gridlines
                ax_left.grid(True, linestyle="--", alpha=0.4, axis="x")

            # Plot other tags (right y-axes)
            for tagname in other_tags:
                if tagname in tag_data:
                    units = self.get_units(tagname)
                    ax_new = ax_left.twinx()
                    ax_new.spines["right"].set_position(("axes", 1 + 0.1 * (len(ax_list) - 1)))
                    label = f"{tagname} {units}"
                    ax_new.plot(
                        timestamps, tag_data[tagname], color=color_cycle[color_idx], label=label
                    )
                    ax_new.set_ylabel(label, color=color_cycle[color_idx])
                    ax_new.tick_params(axis="y", labelcolor=color_cycle[color_idx])
                    ax_new.yaxis.set_major_locator(ticker.MaxNLocator(nbins=5))
                    ax_new.grid(True, linestyle="--", alpha=0.4, axis="y")
                    # Add vertical gridlines for right axes as well (optional, usually not needed)
                    ax_new.grid(True, linestyle="--", alpha=0.4, axis="x")
                    ax_list.append(ax_new)
                    color_idx += 1

            ax_left.set_title(f"{well_name}", fontsize=10)
            ax_left.xaxis.set_major_locator(mdates.AutoDateLocator())
            ax_left.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
            ax_left.tick_params(axis="x", labelrotation=45, labelsize=8)

        # Default to A4 landscape in inches
        width, height = 11.69, 8.27
        fig.set_size_inches(width, height)
        self.pdf_object.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    def add_production_report(self, prod_wells, tagnames):
        """Add production report to PDF."""
        num_wells = len(prod_wells)
        if num_wells == 0:
            return

        fig, axes = plt.subplots(num_wells, 1, sharex=True)
        if num_wells == 1:
            axes = [axes]  # Ensure iterable

        fig.suptitle("Production wells report", fontsize=16, fontweight="bold")
        color_cycle = plt.cm.tab10.colors

        # Separate annulus pressure tags and others, preserving order
        annulus_p_tags = [tn for tn in tagnames if "annulus" in tn.lower()]
        other_tags = [tn for tn in tagnames if "annulus" not in tn.lower()]

        for idx, (well_name, ax_left) in enumerate(zip(prod_wells, axes)):
            self.select_unit(well_name)

            tag_data = {}
            timestamps = None

            # Collect tag data
            for tagname in tagnames:
                value_list, datestamp_list = self.get_data(tagname)
                if not value_list or not datestamp_list:
                    continue
                try:
                    dates = [datetime.fromisoformat(ts.replace("Z", "")) for ts in datestamp_list]
                    if timestamps is None:
                        timestamps = dates
                    tag_data[tagname] = value_list
                except Exception as e:
                    print(f"Error processing tag '{tagname}' for well '{well_name}': {e}")

            if not tag_data or timestamps is None:
                ax_left.set_title(f"{well_name} (No data)")
                ax_left.axis("off")
                continue

            ax_list = [ax_left]
            color_idx = 0

            # Plot annulus pressures (left y-axis)
            for tagname in annulus_p_tags:
                if tagname in tag_data:
                    # Determine units for annulus tags, default to [bar]
                    units = self.get_units(tagname)
                    label = f"{tagname} {units}"
                    ax_left.plot(
                        timestamps, tag_data[tagname], color=color_cycle[color_idx], label=label
                    )
                    ax_left.set_ylabel(label, color=color_cycle[color_idx])
                    ax_left.tick_params(axis="y", labelcolor=color_cycle[color_idx])
                    ax_left.yaxis.set_major_locator(ticker.MaxNLocator(nbins=5))
                    ax_left.grid(True, linestyle="--", alpha=0.4, axis="y")
                    ax_left.grid(True, linestyle="--", alpha=0.4, axis="x")  # vertical gridlines
                    color_idx += 1
            else:
                # If no annulus pressure tag found, still add vertical gridlines on left axis
                ax_left.grid(True, linestyle="--", alpha=0.4, axis="x")

            # Plot other tags (right y-axes)
            for tagname in other_tags:
                if tagname in tag_data:
                    # Units for other tags, extend if needed
                    units = self.get_units(tagname)
                    ax_new = ax_left.twinx()
                    ax_new.spines["right"].set_position(("axes", 1 + 0.1 * (len(ax_list) - 1)))
                    label = f"{tagname} {units}"
                    ax_new.plot(
                        timestamps, tag_data[tagname], color=color_cycle[color_idx], label=label
                    )
                    ax_new.set_ylabel(label, color=color_cycle[color_idx])
                    ax_new.tick_params(axis="y", labelcolor=color_cycle[color_idx])
                    ax_new.yaxis.set_major_locator(ticker.MaxNLocator(nbins=5))
                    ax_new.grid(True, linestyle="--", alpha=0.4, axis="y")
                    ax_new.grid(True, linestyle="--", alpha=0.4, axis="x")
                    ax_list.append(ax_new)
                    color_idx += 1

            ax_left.set_title(f"{well_name}", fontsize=10)
            ax_left.xaxis.set_major_locator(mdates.AutoDateLocator())
            ax_left.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
            ax_left.tick_params(axis="x", labelrotation=45, labelsize=8)

        width, height = 11.69, 8.27
        fig.set_size_inches(width, height)
        self.pdf_object.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    def add_esp_report(self, esps, options):
        """Add ESP report to PDF."""
        rcParams["figure.figsize"] = [11.69, 8.27]  # A4 landscape
        color_cycle = plt.cm.tab10.colors
        plots_per_page = 6  # 2 columns x 3 rows
        ncols = 2
        nrows = 3

        for esp in esps:
            self.select_unit(esp)

            selected_plots = [
                (key, opt["tagname"], opt.get("min"), opt.get("max"))
                for key, opt in options.items()
                if opt.get("checked") and "tagname" in opt
            ]

            total_plots = len(selected_plots)
            total_pages = ceil(total_plots / plots_per_page)

            for page_index in range(total_pages):
                fig, axes = plt.subplots(nrows=nrows, ncols=ncols, sharex=True)
                axes = axes.flatten()

                fig.suptitle(
                    f"ESP Report - {esp} - Page {page_index + 1}", fontsize=16, fontweight="bold"
                )
                fig.subplots_adjust(
                    left=0.06, right=0.95, top=0.88, bottom=0.10, wspace=0.2, hspace=0.5
                )

                for i in range(plots_per_page):
                    subplot_index = page_index * plots_per_page + i
                    if subplot_index >= total_plots:
                        axes[i].axis("off")
                        continue

                    key, tagname, min_val, max_val = selected_plots[subplot_index]
                    ax = axes[i]

                    value_list, datestamp_list = self.get_data(tagname)
                    if not value_list or not datestamp_list:
                        ax.set_title(f"{tagname} (No data)")
                        ax.axis("off")
                        continue

                    try:
                        timestamps = [
                            datetime.fromisoformat(ts.replace("Z", "")) for ts in datestamp_list
                        ]
                    except Exception as e:
                        print(f"Error processing tag '{tagname}' for ESP '{esp}': {e}")
                        ax.set_title(f"{tagname} (Error)")
                        ax.axis("off")
                        continue

                    units = self.get_units(tagname)
                    color = color_cycle[i % len(color_cycle)]

                    ax.plot(timestamps, value_list, color=color)
                    ax.tick_params(axis="y", labelcolor=color)
                    ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=5))
                    ax.grid(True, linestyle="--", alpha=0.4, axis="both")

                    # Add min/max lines and fill regions
                    try:
                        if min_val is not None:
                            min_float = float(min_val)
                            ax.axhline(y=min_float, color="green", linestyle="dotted", linewidth=1)
                            ax.fill_between(
                                timestamps, ax.get_ylim()[0], min_float, color="#d6f5d6", alpha=0.4
                            )
                    except ValueError:
                        pass  # Ignore invalid min_val

                    try:
                        if max_val is not None:
                            max_float = float(max_val)
                            ax.axhline(y=max_float, color="green", linestyle="dotted", linewidth=1)
                            ax.fill_between(
                                timestamps, max_float, ax.get_ylim()[1], color="#d6f5d6", alpha=0.4
                            )
                    except ValueError:
                        pass  # Ignore invalid max_val

                    ax.set_title(f"{tagname} {units}", fontsize=10)
                    ax.set_xlabel("Date")
                    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
                    ax.tick_params(axis="x", labelrotation=45, labelsize=8)

                for j in range(len(selected_plots) % plots_per_page, plots_per_page):
                    if (page_index * plots_per_page + j) >= total_plots:
                        axes[j].axis("off")

                for ax in axes:
                    ax.tick_params(axis="x", labelbottom=True, pad=2)

                fig.set_size_inches(11.69, 8.27)  # A4 landscape
                self.pdf_object.savefig(fig, bbox_inches="tight")
                plt.close(fig)

    def add_stats_table(self, inj_wells, prod_wells):
        """Add statistics table to PDF."""
        all_stats_data = []

        # Tagnames for values to be added in the stats table
        inj_well_tagnames = [
            "injectionwell_flow.measured",
            "injectionwell_wellhead_pressure.measured",
            "injectionwell_annulus_pressure.measured",
        ]
        prod_well_tagnames = ["productionwell_annulus_a_pressure.measured"]

        # First add injection well stats, then production well stats
        all_stats_data += self.gather_stats(inj_wells, inj_well_tagnames)
        all_stats_data += self.gather_stats(prod_wells, prod_well_tagnames)

        if not all_stats_data:
            return  # Skip if no valid stats found

        # Create DataFrame
        df = pd.DataFrame(
            all_stats_data,
            columns=[
                "Unit Name",
                "Tag Name",
                "Min Value",
                "Max Value",
                "Mean Value",
                "Std Dev",
                "Timestamp of Max",
            ],
        )

        # Create figure and table
        fig, ax = plt.subplots()
        ax.axis("tight")
        ax.axis("off")

        ax.set_title(
            f"Summary table for the period {self.start_datestamp_title} - "
            f"{self.end_datestamp_title}",
            fontsize=14,
            fontweight="bold",
            pad=20,
        )

        table = ax.table(
            cellText=df.values,
            colLabels=df.columns,
            cellLoc="center",
            loc="center",
            colColours=["lightgray"] * df.shape[1],
        )

        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.auto_set_column_width(col=list(range(len(df.columns))))

        # Save figure to PDF
        width, height = 11.69, 8.27
        fig.set_size_inches(width, height)
        self.pdf_object.savefig(fig, bbox_inches="tight", pad_inches=0.5)
        plt.close(fig)

    def add_cross_plot(self, units, tagnames, plot_type):
        """Add cross plot to PDF."""
        num_units = len(units)
        if num_units == 0 or len(tagnames) < 3:
            print("Insufficient input: need at least one unit and three tagnames.")
            return

        # Layout: Try to form a near-square grid
        ncols = ceil(sqrt(num_units))
        nrows = ceil(num_units / ncols)

        fig, axes = plt.subplots(nrows, ncols, sharex=False, sharey=False, constrained_layout=True)

        # Normalize axes to 2D list
        axes = np.array(axes).reshape(nrows, ncols)

        for idx, unit_name in enumerate(units):
            row, col = divmod(idx, ncols)
            ax = axes[row][col]

            self.select_unit(unit_name)
            tagname_y = tagnames[0]
            tagname_x = tagnames[1]
            tagname_z = tagnames[2]

            y_data, _ = self.get_data(tagname_y)
            x_data, _ = self.get_data(tagname_x)

            if not y_data or not x_data:
                print(f"[{unit_name}] Missing data for x or y tag.")
                ax.set_title(f"{unit_name} (No data)")
                ax.axis("off")
                continue

            if tagname_z.lower() == "datestamp":
                _, datestamps_z = self.get_data(tagname_y)  # shared timestamps
                try:
                    z_datetimes = [
                        datetime.fromisoformat(ts.replace("Z", "")) for ts in datestamps_z
                    ]
                    z_data = [dt.timestamp() for dt in z_datetimes]
                    z_units = ""
                except Exception as e:
                    print(f"[{unit_name}] Failed to parse datestamp for z: {e}")
                    ax.set_title(f"{unit_name} (Invalid datestamp)")
                    ax.axis("off")
                    continue
            else:
                z_data, _ = self.get_data(tagname_z)
                if not z_data:
                    print(f"[{unit_name}] Missing data for z tag.")
                    ax.set_title(f"{unit_name} (No z data)")
                    ax.axis("off")
                    continue
                z_units = self.get_units(tagname_z)
                z_datetimes = None

            x_units = self.get_units(tagname_x)
            y_units = self.get_units(tagname_y)

            # Scatter plot
            scatter = ax.scatter(x_data, y_data, c=z_data, cmap="viridis", edgecolors="none")
            ax.set_title(f"{unit_name}", fontsize=10)
            ax.set_xlabel(f"{tagname_x} {x_units}", fontsize=8)
            ax.set_ylabel(f"{tagname_y} {y_units}", fontsize=8)
            ax.tick_params(labelsize=8)

            # Colorbar
            cbar = fig.colorbar(scatter, ax=ax)
            if tagname_z.lower() == "datestamp" and z_datetimes:
                formatter = ticker.FuncFormatter(
                    lambda val, pos: datetime.fromtimestamp(val).strftime("%m/%d %H:%M")
                )
                cbar.ax.yaxis.set_major_formatter(formatter)
                cbar.set_label(f"{tagname_z}", fontsize=8)
            else:
                cbar.set_label(f"{tagname_z} {z_units}", fontsize=8)

        # Turn off unused subplots
        total_axes = nrows * ncols
        if total_axes > num_units:
            for empty_idx in range(num_units, total_axes):
                row, col = divmod(empty_idx, ncols)
                axes[row][col].axis("off")

        # Title
        fig.suptitle(f"{plot_type} Cross Plots", fontsize=14, fontweight="bold")

        # A4 landscape size
        fig.set_size_inches(11.69, 8.27)
        self.pdf_object.savefig(fig, bbox_inches="tight", pad_inches=0.3)
        plt.close(fig)

    def convert_numeric_values(self, inputs):
        """Convert numeric values in inputs."""
        for key, val in inputs.items():
            # Try to convert to float first
            try:
                num = float(val)
                # If no error, check if it can be an int
                if num.is_integer():
                    inputs[key] = int(num)
                else:
                    inputs[key] = num
            except (ValueError, TypeError):
                # Not a number, leave as is
                pass
        return inputs

    def add_cross_plot_with_skin_lines(self, units, tagnames, inputs):
        """Add cross plot with skin lines to PDF."""
        # Make sure numeric values are not in string format
        inputs = self.convert_numeric_values(inputs)

        num_units = len(units)
        if num_units == 0 or len(tagnames) < 3:
            print("Insufficient input: need at least one unit and three tagnames.")
            return

        ncols = ceil(sqrt(num_units))
        nrows = ceil(num_units / ncols)

        fig, axes = plt.subplots(nrows, ncols, sharex=False, sharey=False, constrained_layout=True)
        axes = np.array(axes).reshape(nrows, ncols)

        cmap = plt.cm.plasma

        colors = [
            cmap(i / (inputs["no_interval_skin_plot"] - 1))
            for i in range(inputs["no_interval_skin_plot"])
        ]

        for idx, unit_name in enumerate(units):
            row, col = divmod(idx, ncols)
            ax = axes[row][col]

            self.select_unit(unit_name)

            tagname_y, tagname_x, tagname_z = tagnames[:3]

            y_data, _ = self.get_data(tagname_y)  # Pressure in bar
            x_data, _ = self.get_data(tagname_x)  # Flow in m³/h

            if not y_data or not x_data:
                print(f"[{unit_name}] Missing data for x or y tag.")
                ax.set_title(f"{unit_name} (No data)")
                ax.axis("off")
                continue

            skin_array = np.linspace(
                inputs["min_skin_plot"], inputs["max_skin_plot"], inputs["no_interval_skin_plot"]
            )
            flow_array = np.linspace(
                inputs["min_flow_plot"] / 3600,
                inputs["max_flow_plot"] / 3600,
                inputs["no_interval_flow_plot"],
            )

            # Compute skin lines matrix
            inputs["well_name"] = unit_name
            skin_results = self.compute_skin_lines(inputs, flow_array, skin_array)
            pressure_matrix = skin_results["injection_pressure"]

            # Z data for coloring scatter
            if tagname_z.lower() == "datestamp":
                _, datestamps_z = self.get_data(tagname_y)
                try:
                    z_datetimes = [
                        datetime.fromisoformat(ts.replace("Z", "")) for ts in datestamps_z
                    ]
                    z_data = [dt.timestamp() for dt in z_datetimes]
                    z_units = ""
                except Exception as e:
                    print(f"[{unit_name}] Failed to parse datestamp for z: {e}")
                    ax.set_title(f"{unit_name} (Invalid datestamp)")
                    ax.axis("off")
                    continue
            else:
                z_data, _ = self.get_data(tagname_z)
                if not z_data:
                    print(f"[{unit_name}] Missing data for z tag.")
                    ax.set_title(f"{unit_name} (No z data)")
                    ax.axis("off")
                    continue
                z_units = self.get_units(tagname_z)

            x_units = self.get_units(tagname_x)
            y_units = self.get_units(tagname_y)

            # Scatter plot
            scatter = ax.scatter(x_data, y_data, c=z_data, cmap="viridis", edgecolors="none")
            ax.set_title(f"{unit_name}", fontsize=10)
            ax.set_xlabel(f"{tagname_x} {x_units}", fontsize=8)
            ax.set_ylabel(f"{tagname_y} {y_units}", fontsize=8)
            ax.tick_params(labelsize=8)

            # Plot skin lines (flow in m³/h, pressure in bar)
            flow_hr = flow_array * 3600
            for i, skin in enumerate(skin_array):
                ax.plot(
                    flow_hr,
                    pressure_matrix[i],
                    color=colors[i],
                    linestyle="dotted",
                    linewidth=1,
                    label=f"Skin = {skin}",
                )

            ax.legend(fontsize=8, title="Skin Values")

            # Colorbar
            cbar = fig.colorbar(scatter, ax=ax)
            if tagname_z.lower() == "datestamp":
                formatter = ticker.FuncFormatter(
                    lambda val, pos: datetime.fromtimestamp(val).strftime("%m/%d %H:%M")
                )
                cbar.ax.yaxis.set_major_formatter(formatter)
            cbar.set_label(f"{tagname_z} {z_units}", fontsize=8)

        # Hide unused axes
        total_axes = nrows * ncols
        if total_axes > num_units:
            for empty_idx in range(num_units, total_axes):
                row, col = divmod(empty_idx, ncols)
                axes[row][col].axis("off")

        fig.suptitle(
            f"{inputs['plot_type']} Cross Plots with Skin Lines", fontsize=14, fontweight="bold"
        )
        fig.set_size_inches(11.69, 8.27)  # A4 landscape
        self.pdf_object.savefig(fig, bbox_inches="tight", pad_inches=0.3)
        plt.close(fig)

    def calculate_total_volume(self, timestamps, flow_rates):
        """Calculate total volume from timestamps and flow rates."""
        if len(timestamps) != len(flow_rates):
            raise ValueError("timestamps and flow_rates must have the same length")

        if len(timestamps) < 2:
            return 0.0, []  # not enough data

        total_volume = 0.0
        interval_volumes = []

        # Convert timestamps into datetime objects
        times = [datetime.strptime(ts.replace("Z", ""), "%Y-%m-%dT%H:%M:%S") for ts in timestamps]

        # Initialize previous valid value
        prev_flow = None

        for i in range(len(times) - 1):
            f0 = flow_rates[i]
            f1 = flow_rates[i + 1]

            # Replace None with previous valid value
            if f0 is None:
                if prev_flow is None:
                    f0 = 0.0  # fallback if first value is None
                else:
                    f0 = prev_flow

            if f1 is None:
                f1 = f0  # use f0 if f1 is None

            # Average flow during this interval
            avg_flow = (f0 + f1) / 2.0

            # Time difference in hours
            delta_hours = (times[i + 1] - times[i]).total_seconds() / 3600.0

            # Interval volume
            interval_volume = avg_flow * delta_hours

            interval_volumes.append(interval_volume)
            total_volume += interval_volume

            # Update prev_flow
            prev_flow = f1

        return total_volume, interval_volumes

    def weighted_average_value_with_volume(self, values, timestamps, volume_intervals):
        """Calculate the volume-weighted average of a value over time."""
        if len(values) != len(timestamps):
            raise ValueError("values and timestamps must have the same length")

        if len(volume_intervals) != len(timestamps) - 1:
            raise ValueError("volume_intervals length must be len(timestamps)-1")

        if len(volume_intervals) == 0:
            return 0.0  # nothing to average

        # -------------------------
        # Interpolate None values
        # -------------------------
        values_interp = values.copy()
        n = len(values_interp)

        # Find indices of valid values
        valid_indices = [i for i, v in enumerate(values_interp) if v is not None]

        if not valid_indices:
            return 0.0  # all values are None

        for i in range(n):
            if values_interp[i] is None:
                # find previous and next valid indices
                prev_idx = max([vi for vi in valid_indices if vi < i], default=None)
                next_idx = min([vi for vi in valid_indices if vi > i], default=None)

                if prev_idx is None:
                    # Use next valid value
                    values_interp[i] = values_interp[next_idx]
                elif next_idx is None:
                    # Use previous valid value
                    values_interp[i] = values_interp[prev_idx]
                else:
                    # Linear interpolation
                    prev_val = values_interp[prev_idx]
                    next_val = values_interp[next_idx]
                    values_interp[i] = prev_val + (next_val - prev_val) * (i - prev_idx) / (
                        next_idx - prev_idx
                    )

        # -------------------------
        # Compute weighted average
        # -------------------------
        weighted_sum = 0.0
        total_volume = 0.0

        for i in range(len(volume_intervals)):
            # average value in this interval
            avg_value = (values_interp[i] + values_interp[i + 1]) / 2.0

            # multiply by interval volume
            weighted_sum += avg_value * volume_intervals[i]

            # sum total volume
            total_volume += volume_intervals[i]

        if total_volume == 0:
            return 0.0

        return weighted_sum / total_volume

    def format_value(self, val):
        """Change the format of a value."""
        if isinstance(val, (float, int)):
            return f"{val:.2f}"
        else:
            return str(val)

    def add_nlog_data(self, LicenseHolder, NlogPeriod, df_prod, df_inj, table3_df):
        """Load the NLOG EXCEL template and writes the data."""
        # Build template path
        if not hasattr(self, "project_path") or not self.project_path:
            raise ValueError("self.project_path is not set or is empty.")

        template_path = os.path.join(
            self.project_path,
            "_template",
            "report_generator",
            "aardwarmte_productiecijfers_template_v2025.xlsm",
        )

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"NLOG template not found at: {template_path}")

        # Load workbook (keep formatting, keep_vba, keep formulas)
        wb = load_workbook(template_path, keep_vba=True, data_only=False)

        if "Aardwarmte" not in wb.sheetnames:
            raise ValueError('Sheet "Aardwarmte" not found in nlog_template.xlsm')

        ws = wb["Aardwarmte"]

        # --------------------------------------------------------------------------------------------
        # Write metadata (preserve formatting: only write values)
        # --------------------------------------------------------------------------------------------
        ws["B4"].value = LicenseHolder

        # NlogPeriod like "2025-05" -> "202505"
        nlog_period_compact = str(NlogPeriod).replace("-", "")
        ws["B5"].value = nlog_period_compact

        def _write_df_at(start_coord, df):
            if df is None or df.empty:
                return

            col_letter, start_row = coordinate_from_string(start_coord)
            start_col = column_index_from_string(col_letter)

            # Write values only (no headers), do not insert/delete rows/cols.
            for r_idx, row_vals in enumerate(df.itertuples(index=False, name=None), start=0):
                for c_idx, value in enumerate(row_vals, start=0):
                    ws.cell(row=start_row + r_idx, column=start_col + c_idx).value = value

        # df_prod -> A9 (unchanged)
        _write_df_at("A9", df_prod)

        # df_inj -> skip first row, start at M9
        if df_inj is not None and not df_inj.empty:
            df_inj_trimmed = df_inj.drop(columns=["well_name"])
            _write_df_at("M9", df_inj_trimmed)

        # Add Mining work table data
        _write_df_at("A28", table3_df)

        return wb

    def get_unit_data(self, units, table_tagnames, use_plant_units_fallback=False):
        """Retrieve data for given units and tagnames from database."""
        table_data = {}
        for unit_name in units:
            self.select_unit(unit_name)
            table_data[unit_name] = {}

            for column_name in table_tagnames.keys():
                tagname = table_tagnames[column_name]["tagname"]
                unit_type = table_tagnames[column_name]["unit"]

                # Select correct unit
                self.select_unit(unit_name)
                if unit_type not in unit_name:
                    found = False

                    # First try: from connected units
                    for unit in self.unit.to_units:
                        if unit_type in unit.name:
                            self.select_unit(unit.name)
                            found = True
                            break

                    # Optional fallback: search through all plant units (used for injection)
                    if use_plant_units_fallback and not found:
                        for plant_unit in self.plant.units:
                            if unit_type in plant_unit.name:
                                self.select_unit(plant_unit.name)
                                break

                # Fetch data
                if tagname not in ["unknown", "loaded", "previous_tagname"]:
                    value_list, datestamp_list = self.get_data(tagname)
                    if not value_list:
                        table_data[unit_name][column_name] = {
                            "values": [],
                            "datestamps": [],
                            "status": "No data found",
                        }
                    else:
                        table_data[unit_name][column_name] = {
                            "values": value_list,
                            "datestamps": datestamp_list,
                            "status": "loaded",
                        }
                else:
                    table_data[unit_name][column_name] = {
                        "values": [],
                        "datestamps": [],
                        "status": tagname,
                    }

        return table_data

    def calculate_total_heat_extracted_MJ(self, hex_data):
        """Calculate the total heat extracted from heat exchanger measured data."""
        rho_kg_m3 = 1000.0
        cp_J_kgK = 4186.0

        def _parse_utc(ts: str) -> datetime:
            # Handles '...Z' and also already-offset strings.
            ts = ts.strip()
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts).astimezone(timezone.utc)

        def _series_from(signal):
            vals = signal.get("values", []) or []
            dts = signal.get("datestamps", []) or []
            if len(vals) != len(dts) or len(vals) == 0:
                return pd.Series(dtype="float64")

            idx = pd.to_datetime([_parse_utc(t) for t in dts], utc=True)
            s = pd.Series(list(vals), index=idx)

            # Convert to numeric; non-numeric -> NaN
            s = pd.to_numeric(s, errors="coerce")

            # If duplicates exist, keep the last reading per timestamp
            s = s[~s.index.duplicated(keep="last")].sort_index()
            return s

        total_J = 0.0

        for key, hx in (hex_data or {}).items():
            if "heat_exchanger" not in str(key):
                continue
            if not isinstance(hx, dict):
                continue

            # If you want to enforce status, uncomment:
            # if hx.get("status") not in ("loaded", "ok", True):
            #     continue

            flow_s = _series_from(hx.get("hex_secondary_flow", {}))
            tin_s = _series_from(hx.get("hex_secondary_inlet_temperature", {}))
            tout_s = _series_from(hx.get("hex_secondary_outlet_temperature", {}))

            if flow_s.empty or tin_s.empty or tout_s.empty:
                continue

            # Union of timestamps across signals
            union_index = flow_s.index.union(tin_s.index).union(tout_s.index).sort_values()

            df = pd.DataFrame(
                {
                    "flow_m3h": flow_s.reindex(union_index),
                    "tin_C": tin_s.reindex(union_index),
                    "tout_C": tout_s.reindex(union_index),
                },
                index=union_index,
            )

            # Interpolate in time (linear), consistent with "average between measured values"
            df = df.interpolate(method="time", limit_direction="both")

            # Compute interval energy using average of endpoints (trapezoid)
            t = df.index
            for i in range(len(df) - 1):
                t0 = t[i]
                t1 = t[i + 1]
                dt_s = (t1 - t0).total_seconds()
                if dt_s <= 0:
                    continue

                f0, f1 = df.iloc[i]["flow_m3h"], df.iloc[i + 1]["flow_m3h"]
                ti0, ti1 = df.iloc[i]["tin_C"], df.iloc[i + 1]["tin_C"]
                to0, to1 = df.iloc[i]["tout_C"], df.iloc[i + 1]["tout_C"]

                # Skip intervals with NaN
                if (
                    pd.isna(f0)
                    or pd.isna(f1)
                    or pd.isna(ti0)
                    or pd.isna(ti1)
                    or pd.isna(to0)
                    or pd.isna(to1)
                ):
                    continue

                flow_avg_m3h = 0.5 * (float(f0) + float(f1))
                tin_avg = 0.5 * (float(ti0) + float(ti1))
                tout_avg = 0.5 * (float(to0) + float(to1))

                dT_K = tout_avg - tin_avg
                # If you want to ignore negative extraction, uncomment:
                # if dT_K <= 0:
                #     continue

                m_dot_kg_s = (flow_avg_m3h * rho_kg_m3) / 3600.0
                Q_J = m_dot_kg_s * cp_J_kgK * dT_K * dt_s
                total_J += Q_J

        return total_J / 1_000_000.0  # MJ

    def calculate_esp_operational_hours_and_kwh(self, esp_data):
        """Calculate the total number of operational hours and the total power consumption."""
        current_threshold = 2.0
        power_factor = 1.0
        include_sqrt3 = False

        def _parse_utc(ts):
            ts = ts.strip()
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts).astimezone(timezone.utc)

        def _series_from(signal):
            vals = signal.get("values", []) or []
            dts = signal.get("datestamps", []) or []
            if len(vals) == 0 or len(vals) != len(dts):
                return pd.Series(dtype="float64")

            idx = pd.to_datetime([_parse_utc(t) for t in dts], utc=True)
            s = pd.Series(list(vals), index=idx)
            s = pd.to_numeric(s, errors="coerce")
            s = s[~s.index.duplicated(keep="last")].sort_index()
            return s

        if not esp_data:
            return 0.0, 0.0

        esp_keys = [k for k in esp_data.keys() if str(k).startswith("esp_")]
        if not esp_keys:
            return 0.0, 0.0

        total_running_hours_all_esps = 0.0
        total_energy_Wh_all_esps = 0.0

        sqrt3 = sqrt(3.0)

        for esp_key in esp_keys:
            esp = esp_data.get(esp_key, {})
            if not isinstance(esp, dict):
                continue

            esp_current = _series_from(esp.get("esp_current", {}))
            esp_voltage = _series_from(esp.get("esp_voltage", {}))

            if esp_current.empty or esp_voltage.empty:
                continue

            # Align on union of timestamps and interpolate in time
            idx = esp_current.index.union(esp_voltage.index).sort_values()
            df = pd.DataFrame(
                {"esp_current": esp_current.reindex(idx), "esp_voltage": esp_voltage.reindex(idx)},
                index=idx,
            )
            df = df.interpolate(method="time", limit_direction="both")

            # Integrate over intervals
            for i in range(len(df) - 1):
                t0, t1 = df.index[i], df.index[i + 1]
                dt_s = (t1 - t0).total_seconds()
                if dt_s <= 0:
                    continue

                I0, I1 = df.iloc[i]["esp_current"], df.iloc[i + 1]["esp_current"]
                V0, V1 = df.iloc[i]["esp_voltage"], df.iloc[i + 1]["esp_voltage"]
                if pd.isna(I0) or pd.isna(I1) or pd.isna(V0) or pd.isna(V1):
                    continue

                I_avg = 0.5 * (float(I0) + float(I1))
                V_avg = 0.5 * (float(V0) + float(V1))

                dt_h = dt_s / 3600.0

                # Running time rule
                if I_avg >= current_threshold:
                    total_running_hours_all_esps += dt_h

                # Power + energy
                P_W = V_avg * I_avg * float(power_factor)
                if include_sqrt3:
                    P_W *= sqrt3

                total_energy_Wh_all_esps += P_W * dt_h  # W * h = Wh

        num_esps = len(esp_keys)
        operational_hours = total_running_hours_all_esps / num_esps if num_esps > 0 else 0.0
        electricity_consumption_kWh = total_energy_Wh_all_esps / 1000.0

        return operational_hours, electricity_consumption_kWh

    def add_nlog_report(
        self,
        LicenseHolder,
        NlogPeriod,
        inj_wells,
        prod_wells,
        esps,
        hexs,
        prod_table_tagnames,
        inj_table_tagnames,
        esp_tagnames,
        hex_tagnames,
    ):
        """Prepare NLOG report data and return Excel file as BytesIO."""
        prod_table_data = self.get_unit_data(
            prod_wells, prod_table_tagnames, use_plant_units_fallback=False
        )
        inj_table_data = self.get_unit_data(
            inj_wells, inj_table_tagnames, use_plant_units_fallback=True
        )
        hex_data = self.get_unit_data(hexs, hex_tagnames, use_plant_units_fallback=True)
        esp_data = self.get_unit_data(esps, esp_tagnames, use_plant_units_fallback=True)

        # ------------------------------------------------------------------------------------------------
        #                                   Prepare DataFrames
        # ------------------------------------------------------------------------------------------------
        prod_table_rows = []
        for well_name in prod_wells:
            row = {"well_name": well_name}

            # Water production volume
            if prod_table_data[well_name]["water_prod_volume"]["status"] == "loaded":
                total_volume, _ = self.calculate_total_volume(
                    prod_table_data[well_name]["water_prod_volume"]["datestamps"],
                    prod_table_data[well_name]["water_prod_volume"]["values"],
                )
                row["water_prod_volume"] = total_volume
            else:
                row["water_prod_volume"] = "No data found"

            # Production pressure average
            if prod_table_data[well_name]["prod_pressure_avg"]["status"] == "loaded":
                _, volume_intervals = self.calculate_total_volume(
                    prod_table_data[well_name]["water_prod_volume"]["datestamps"],
                    prod_table_data[well_name]["water_prod_volume"]["values"],
                )
                row["prod_pressure_avg"] = self.weighted_average_value_with_volume(
                    prod_table_data[well_name]["prod_pressure_avg"]["values"],
                    prod_table_data[well_name]["prod_pressure_avg"]["datestamps"],
                    volume_intervals,
                )
            else:
                row["prod_pressure_avg"] = "No data found"

            # Production pressure min
            values = prod_table_data[well_name]["prod_pressure_avg"]["values"]
            row["prod_pressure_min"] = (
                min(v for v in values if v is not None) if values else "No data found"
            )

            # Well pressure average
            if prod_table_data[well_name]["well_pressure_avg"]["status"] == "loaded":
                _, volume_intervals = self.calculate_total_volume(
                    prod_table_data[well_name]["water_prod_volume"]["datestamps"],
                    prod_table_data[well_name]["water_prod_volume"]["values"],
                )
                row["well_pressure_avg"] = self.weighted_average_value_with_volume(
                    prod_table_data[well_name]["well_pressure_avg"]["values"],
                    prod_table_data[well_name]["well_pressure_avg"]["datestamps"],
                    volume_intervals,
                )
            else:
                row["well_pressure_avg"] = "No data found"

            prod_table_rows.append(row)

        inj_table_rows = []
        for well_name in inj_wells:
            row = {"well_name": well_name}

            if inj_table_data[well_name]["water_inj_volume"]["status"] == "loaded":
                total_volume, _ = self.calculate_total_volume(
                    inj_table_data[well_name]["water_inj_volume"]["datestamps"],
                    inj_table_data[well_name]["water_inj_volume"]["values"],
                )
                row["water_inj_volume"] = total_volume
            else:
                row["water_inj_volume"] = "No data found"

            if inj_table_data[well_name]["inj_temperature_avg"]["status"] == "loaded":
                _, volume_intervals = self.calculate_total_volume(
                    inj_table_data[well_name]["water_inj_volume"]["datestamps"],
                    inj_table_data[well_name]["water_inj_volume"]["values"],
                )
                row["inj_temperature_avg"] = self.weighted_average_value_with_volume(
                    inj_table_data[well_name]["inj_temperature_avg"]["values"],
                    inj_table_data[well_name]["inj_temperature_avg"]["datestamps"],
                    volume_intervals,
                )
            else:
                row["inj_temperature_avg"] = "No data found"

            if inj_table_data[well_name]["inj_pump_pressure_avg"]["status"] == "loaded":
                values = inj_table_data[well_name]["inj_pump_pressure_avg"]["values"]
                row["inj_pump_pressure_avg"] = sum(values) / len(values)
                row["inj_pump_pressure_max"] = max(v for v in values if v is not None)
            else:
                row["inj_pump_pressure_avg"] = "No data found"
                row["inj_pump_pressure_max"] = "No data found"

            inj_table_rows.append(row)

        df_prod = pd.DataFrame(prod_table_rows)
        df_inj = pd.DataFrame(inj_table_rows)

        # Create Mining work table dataframe
        operational_hours, electricity_consumption_kWh = (
            self.calculate_esp_operational_hours_and_kwh(esp_data)
        )
        table3_dictionary = {
            "mining_work_tile": "Doublet 1",
            "total_extracted_heat": self.calculate_total_heat_extracted_MJ(hex_data),
            "operational_hours": operational_hours,
            "electricity_consumption_kWh": electricity_consumption_kWh,
        }

        table3_df = pd.DataFrame([table3_dictionary])

        # ------------------------------------------------------------------------------------------------
        #                                   Load & modify Excel
        # ------------------------------------------------------------------------------------------------
        wb = self.add_nlog_data(LicenseHolder, NlogPeriod, df_prod, df_inj, table3_df)

        # ------------------------------------------------------------------------------------------------
        #                                   Return BytesIO for download
        # ------------------------------------------------------------------------------------------------
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    def wrap_text(self, text, max_chars_per_line=90):
        """Change line in text output."""
        import textwrap

        return "\n".join(textwrap.wrap(text, max_chars_per_line))

    def add_text_section_page(self, user_text, section_title="User Input Section"):
        """Include the text section as a page."""
        # Check if user text is provided
        if not user_text or not user_text.strip():
            print("No user text input provided, skipping text section.")
            return

        # Prepare wrapped lines as a list of strings
        wrapped_lines = self.wrap_text(user_text, max_chars_per_line=90).split("\n")

        # A4 landscape size in inches
        # page_width, page_height = 11.69, 8.27

        # Parameters for text layout
        font_size = 12
        line_height = font_size * 1.2 / 72  # roughly converted from pts to inches (1pt=1/72 inch)
        top_margin = 0.8  # inches from top for title separation
        left_margin = 0.5
        # right_margin = 0.5
        bottom_margin = 0.5
        usable_height = self.page_size[0] - top_margin - bottom_margin

        # Number of lines that fit on one page
        max_lines_per_page = int(usable_height // line_height)

        # Split wrapped_lines into chunks fitting on pages
        chunks = [
            wrapped_lines[i : i + max_lines_per_page]
            for i in range(0, len(wrapped_lines), max_lines_per_page)
        ]

        for i, chunk in enumerate(chunks):
            fig, ax = plt.subplots(figsize=(self.page_size[0], self.page_size[1]))

            # Title only on first page or optionally on each page
            if i == 0:
                fig.suptitle(section_title, fontsize=16, fontweight="bold", y=0.95)

            ax.axis("off")

            # Join lines for this chunk and add text starting below title area
            # relative position for ax.text y coordinate
            y_start = 1 - top_margin / self.page_size[1]
            text = "\n".join(chunk)
            ax.text(
                left_margin / self.page_size[0],
                y_start,
                text,
                fontsize=font_size,
                va="top",
                ha="left",
                wrap=True,
                transform=ax.transAxes,
            )

            self.pdf_object.savefig(fig, bbox_inches="tight", pad_inches=0.3)
            plt.close(fig)

    def export_pdf(self):
        """Export PDF report."""
        self.pdf_object.close()
        print("Plots exported to plots.pdf")

        # Move to the beginning of the buffer
        self.pdf_buffer.seek(0)
