# plot_latency.py
# Script to plot latency data from CSV files

import argparse
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import glob
import os
from datetime import datetime

def load_latency_data(file_path):
    """Load latency data from a CSV file"""
    try:
        # Read the CSV file
        df = pd.read_csv(file_path)
        print(f"Loaded data from {file_path}")
        print(f"Found {len(df)} data points")
        return df
    except Exception as e:
        print(f"Error loading data from {file_path}: {e}")
        return None

def plot_latency_graph(data, title=None, output_file=None, show_encryption=True, y_range=200):
    """Plot latency data"""
    if data is None or len(data) == 0:
        print("No data to plot")
        return
    
    # Create figure with subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1]})
    
    # Extract data
    message_ids = data['message_id']
    latencies = data['round_trip_latency_ms']
    
    # Calculate statistics
    min_latency = latencies.min()
    max_latency = latencies.max()
    avg_latency = latencies.mean()
    median_latency = latencies.median()
    std_dev = latencies.std()
    
    # Calculate percentiles
    percentiles = np.percentile(latencies, [90, 95, 99])
    p90, p95, p99 = percentiles
    
    # Plot the main latency graph
    ax1.plot(message_ids, latencies, 'b-', label='Round-trip Latency')
    ax1.axhline(y=avg_latency, color='r', linestyle='--', label=f'Average: {avg_latency:.2f} ms')
    ax1.axhline(y=median_latency, color='g', linestyle='--', label=f'Median: {median_latency:.2f} ms')
    
    # Plot encryption and processing times if available
    if show_encryption and 'encryption_time_ms' in data.columns and 'processing_time_ms' in data.columns:
        encrypt_times = data['encryption_time_ms']
        process_times = data['processing_time_ms']
        
        # Only plot if we have non-zero values
        if encrypt_times.sum() > 0 or process_times.sum() > 0:
            ax1.plot(message_ids, encrypt_times, 'g-', alpha=0.5, label='Encryption Time')
            ax1.plot(message_ids, process_times, 'm-', alpha=0.5, label='Processing Time')
    
    # Set y-axis limits to +/- y_range from median
    y_min = max(0, median_latency - y_range)  # Prevent negative values
    y_max = median_latency + y_range
    ax1.set_ylim(y_min, y_max)
    
    # Set labels and title
    ax1.set_xlabel('Message ID')
    ax1.set_ylabel('Time (ms)')
    if title:
        ax1.set_title(title)
    else:
        ax1.set_title('Latency Measurements')
    
    # Add legend
    ax1.legend()
    
    # Add grid
    ax1.grid(True, alpha=0.3)
    
    # Create histogram in the second subplot
    ax2.hist(latencies, bins=30, color='skyblue', edgecolor='black', alpha=0.7)
    ax2.axvline(x=avg_latency, color='r', linestyle='--', label=f'Average: {avg_latency:.2f} ms')
    ax2.axvline(x=median_latency, color='g', linestyle='--', label=f'Median: {median_latency:.2f} ms')
    ax2.axvline(x=p90, color='orange', linestyle='--', label=f'90th %ile: {p90:.2f} ms')
    ax2.axvline(x=p99, color='purple', linestyle='--', label=f'99th %ile: {p99:.2f} ms')
    
    # Set x-axis limits for histogram to match the latency range +/- y_range from median
    ax2.set_xlim(y_min, y_max)
    
    # Set labels for histogram
    ax2.set_xlabel('Latency (ms)')
    ax2.set_ylabel('Frequency')
    ax2.set_title('Latency Distribution')
    
    # Add legend
    ax2.legend()
    
    # Add grid
    ax2.grid(True, alpha=0.3)
    
    # Add statistics text box
    stats_text = (
        f"Statistics:\n"
        f"Min: {min_latency:.2f} ms\n"
        f"Max: {max_latency:.2f} ms\n"
        f"Avg: {avg_latency:.2f} ms\n"
        f"Median: {median_latency:.2f} ms\n"
        f"Std Dev: {std_dev:.2f} ms\n"
        f"90th %ile: {p90:.2f} ms\n"
        f"95th %ile: {p95:.2f} ms\n"
        f"99th %ile: {p99:.2f} ms\n"
        f"Sample Size: {len(latencies)}"
    )
    
    # Add text box with statistics
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
    ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes, fontsize=10,
            verticalalignment='top', bbox=props)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save figure if output file specified
    if output_file:
        plt.savefig(output_file, dpi=300)
        print(f"Plot saved to {output_file}")
    
    # Show the plot
    plt.show()

def plot_multiple_files(file_paths, title=None, output_file=None, y_range=200):
    """Plot data from multiple files for comparison"""
    if not file_paths:
        print("No files to plot")
        return
    
    # Create figure
    plt.figure(figsize=(12, 8))
    
    # Keep track of all latencies for statistics
    all_latencies = []
    all_medians = []
    
    # Plot each file
    for file_path in file_paths:
        # Load data
        df = load_latency_data(file_path)
        if df is None:
            continue
        
        # Get file name without path and extension for labeling
        file_label = os.path.splitext(os.path.basename(file_path))[0]
        
        # Extract data
        message_ids = df['message_id']
        latencies = df['round_trip_latency_ms']
        all_latencies.append(latencies)
        all_medians.append(latencies.median())
        
        # Plot latency
        plt.plot(message_ids, latencies, '-', label=file_label)
    
    # Calculate the overall median for setting y-axis limits
    if all_medians:
        overall_median = np.median(all_medians)
        # Set y-axis limits to +/- y_range from median
        y_min = max(0, overall_median - y_range)  # Prevent negative values
        y_max = overall_median + y_range
        plt.ylim(y_min, y_max)
    
    # Set labels and title
    plt.xlabel('Message ID')
    plt.ylabel('Latency (ms)')
    if title:
        plt.title(title)
    else:
        plt.title('Latency Comparison')
    
    # Add legend
    plt.legend()
    
    # Add grid
    plt.grid(True, alpha=0.3)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save figure if output file specified
    if output_file:
        plt.savefig(output_file, dpi=300)
        print(f"Plot saved to {output_file}")
    
    # Show the plot
    plt.show()
    
    # If we have multiple files, create a box plot for comparison
    if len(all_latencies) > 1:
        plt.figure(figsize=(10, 6))
        box_plot = plt.boxplot(all_latencies, labels=[os.path.splitext(os.path.basename(f))[0] for f in file_paths])
        
        # Calculate the overall median for setting y-axis limits
        if all_medians:
            overall_median = np.median(all_medians)
            # Set y-axis limits to +/- y_range from median
            y_min = max(0, overall_median - y_range)  # Prevent negative values
            y_max = overall_median + y_range
            plt.ylim(y_min, y_max)
        
        plt.ylabel('Latency (ms)')
        plt.title('Latency Distribution Comparison')
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # Save box plot if output file specified
        if output_file:
            box_plot_file = os.path.splitext(output_file)[0] + '_boxplot.png'
            plt.savefig(box_plot_file, dpi=300)
            print(f"Box plot saved to {box_plot_file}")
        
        plt.show()

def analyze_size_impact(directory, output_file=None, y_range=200):
    """Analyze the impact of message size on latency"""
    # Find all CSV files
    files = glob.glob(os.path.join(directory, '*.csv'))
    if not files:
        print(f"No CSV files found in {directory}")
        return
    
    # Collect data for different sizes
    sizes = []
    avg_latencies = []
    median_latencies = []
    p90_latencies = []
    std_devs = []
    labels = []
    all_medians = []
    
    for file_path in files:
        # Try to extract size from filename
        filename = os.path.basename(file_path)
        size_match = None
        
        # Ask user for the size if we can't determine it
        if size_match is None:
            try:
                size = int(input(f"Enter message size for {filename}: "))
                sizes.append(size)
                labels.append(f"{size} bytes")
            except ValueError:
                print(f"Skipping {filename} - couldn't determine size")
                continue
        
        # Load data
        df = load_latency_data(file_path)
        if df is None:
            continue
        
        # Calculate statistics
        latencies = df['round_trip_latency_ms']
        avg_latencies.append(latencies.mean())
        median = latencies.median()
        median_latencies.append(median)
        all_medians.append(median)
        p90_latencies.append(np.percentile(latencies, 90))
        std_devs.append(latencies.std())
    
    # Create sorted arrays based on sizes
    sorted_indices = np.argsort(sizes)
    sorted_sizes = [sizes[i] for i in sorted_indices]
    sorted_labels = [labels[i] for i in sorted_indices]
    sorted_avg_latencies = [avg_latencies[i] for i in sorted_indices]
    sorted_median_latencies = [median_latencies[i] for i in sorted_indices]
    sorted_p90_latencies = [p90_latencies[i] for i in sorted_indices]
    sorted_std_devs = [std_devs[i] for i in sorted_indices]
    
    # Create figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # Plot average, median, and 90th percentile latencies
    ax1.plot(sorted_sizes, sorted_avg_latencies, 'b-o', label='Average Latency')
    ax1.plot(sorted_sizes, sorted_median_latencies, 'g-o', label='Median Latency')
    ax1.plot(sorted_sizes, sorted_p90_latencies, 'r-o', label='90th Percentile')
    
    # Add error bars
    ax1.errorbar(sorted_sizes, sorted_avg_latencies, yerr=sorted_std_devs, fmt='none', ecolor='gray', capsize=5)
    
    # Calculate the overall median for setting y-axis limits
    if all_medians:
        overall_median = np.median(all_medians)
        # Set y-axis limits to +/- y_range from median
        y_min = max(0, overall_median - y_range)  # Prevent negative values
        y_max = overall_median + y_range
        ax1.set_ylim(y_min, y_max)
    
    # Set labels and title
    ax1.set_xlabel('Message Size (bytes)')
    ax1.set_ylabel('Latency (ms)')
    ax1.set_title('Impact of Message Size on Latency')
    
    # Add legend
    ax1.legend()
    
    # Add grid
    ax1.grid(True, alpha=0.3)
    
    # Create bar chart for standard deviation
    ax2.bar(sorted_labels, sorted_std_devs, color='skyblue', edgecolor='black', alpha=0.7)
    
    # Set labels for bar chart
    ax2.set_xlabel('Message Size')
    ax2.set_ylabel('Standard Deviation (ms)')
    ax2.set_title('Latency Variability by Message Size')
    
    # Add grid
    ax2.grid(True, alpha=0.3, axis='y')
    
    # Adjust layout
    plt.tight_layout()
    
    # Save figure if output file specified
    if output_file:
        plt.savefig(output_file, dpi=300)
        print(f"Size impact plot saved to {output_file}")
    
    # Show the plot
    plt.show()

def create_summary_report(file_path, output_file=None):
    """Create a summary report of latency data"""
    # Load data
    df = load_latency_data(file_path)
    if df is None:
        return
    
    # Calculate statistics
    latencies = df['round_trip_latency_ms']
    min_latency = latencies.min()
    max_latency = latencies.max()
    avg_latency = latencies.mean()
    median_latency = latencies.median()
    std_dev = latencies.std()
    
    # Calculate percentiles
    percentiles = np.percentile(latencies, [25, 50, 75, 90, 95, 99])
    p25, p50, p75, p90, p95, p99 = percentiles
    
    # Check if we have encryption/processing times
    has_encrypt = 'encryption_time_ms' in df.columns
    has_process = 'processing_time_ms' in df.columns
    
    # Create report text
    report = f"""
    LATENCY TEST SUMMARY REPORT
    ==========================
    Filename: {os.path.basename(file_path)}
    Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    
    SAMPLE INFORMATION
    -----------------
    Total samples: {len(df)}
    
    LATENCY STATISTICS (milliseconds)
    ------------------------------
    Minimum: {min_latency:.2f} ms
    Maximum: {max_latency:.2f} ms
    Range: {max_latency - min_latency:.2f} ms
    
    Average: {avg_latency:.2f} ms
    Median: {median_latency:.2f} ms
    Standard Deviation: {std_dev:.2f} ms
    Coefficient of Variation: {(std_dev/avg_latency)*100:.2f}%
    
    PERCENTILES
    ----------
    25th percentile: {p25:.2f} ms
    50th percentile: {p50:.2f} ms (median)
    75th percentile: {p75:.2f} ms
    90th percentile: {p90:.2f} ms
    95th percentile: {p95:.2f} ms
    99th percentile: {p99:.2f} ms
    """
    
    # Add encryption/processing info if available
    if has_encrypt and has_process:
        encrypt_times = df['encryption_time_ms']
        process_times = df['processing_time_ms']
        
        # Only include if we have non-zero values
        if encrypt_times.sum() > 0 or process_times.sum() > 0:
            avg_encrypt = encrypt_times.mean()
            avg_process = process_times.mean()
            total_overhead = avg_encrypt + avg_process
            overhead_percent = (total_overhead / avg_latency) * 100
            
            encrypt_report = f"""
    PROCESSING OVERHEAD
    -----------------
    Average encryption time: {avg_encrypt:.2f} ms
    Average processing time: {avg_process:.2f} ms
    Total processing overhead: {total_overhead:.2f} ms
    Processing percentage of total latency: {overhead_percent:.2f}%
            """
            
            report += encrypt_report
    
    # Print report
    print(report)
    
    # Save report if output file specified
    if output_file:
        with open(output_file, 'w') as f:
            f.write(report)
        print(f"Report saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Plot latency data from CSV files')
    parser.add_argument('--file', help='Path to CSV file with latency data')
    parser.add_argument('--compare', nargs='+', help='Paths to multiple CSV files for comparison')
    parser.add_argument('--size-impact', help='Analyze impact of message size (directory containing multiple CSVs)')
    parser.add_argument('--report', action='store_true', help='Generate a detailed report')
    parser.add_argument('--title', help='Title for the plot')
    parser.add_argument('--output', help='Output file path for the plot')
    parser.add_argument('--no-encryption', action='store_true', help='Don\'t show encryption times on the plot')
    parser.add_argument('--y-range', type=int, default=200, 
                       help='Y-axis range in ms around median (default: 200)')
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    if args.output:
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
    
    # Get the y-range from arguments
    y_range = args.y_range
    
    # Check which mode to run in
    if args.file:
        # Load data
        data = load_latency_data(args.file)
        
        # Generate report if requested
        if args.report:
            report_file = args.output.replace('.png', '_report.txt') if args.output else 'latency_report.txt'
            create_summary_report(args.file, report_file)
        
        # Plot graph
        plot_latency_graph(data, args.title, args.output, not args.no_encryption, y_range)
    elif args.compare:
        # Plot multiple files for comparison
        plot_multiple_files(args.compare, args.title, args.output, y_range)
    elif args.size_impact:
        # Analyze impact of message size
        analyze_size_impact(args.size_impact, args.output, y_range)
    else:
        # No mode specified, check for CSV files in current directory
        files = glob.glob('*.csv')
        if files:
            print("Found the following CSV files:")
            for i, file in enumerate(files):
                print(f"{i+1}. {file}")
            try:
                choice = int(input("Enter the number of the file to plot (0 to exit): "))
                if 1 <= choice <= len(files):
                    data = load_latency_data(files[choice-1])
                    plot_latency_graph(data, f"Latency from {files[choice-1]}", None, True, y_range)
                elif choice != 0:
                    print("Invalid choice")
            except ValueError:
                print("Invalid input")
        else:
            print("No CSV files found. Please specify a file with --file or a directory with --size-impact")
            parser.print_help()

if __name__ == "__main__":
    main()