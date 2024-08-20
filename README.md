<center>
<img src='app/static/img/glimpser.png'>
</center>

# Glimpser

## Introduction
Glimpser is a straightforward yet powerful real-time monitoring application designed to capture, analyze, and summarize live data from various sources such as cameras, dashboards, and video streams. Utilizing advanced image processing techniques and AI models, Glimpser provides insightful summaries and alerts. It’s highly configurable, allowing users to tailor it to their specific monitoring needs through an easy-to-use interface.

![Peek2024-08-0721-25-ezgif com-optimize](https://github.com/user-attachments/assets/44ddcbd5-31f1-4ff9-954a-954a85479dc0)

## Features
- **Real-time Monitoring**: Continuously captures data from multiple sources. Whether it's a traffic camera or a weather dashboard, Glimpser ensures you’re always up-to-date with the latest information.

- **Image Processing**: Employs advanced techniques to compare images and detect even subtle changes, making it ideal for monitoring evolving situations effectively.

- **Motion Detection**: Automatically detects motion in the captured images and videos, triggering alerts and actions as configured by the user.

- **AI Integration**: Integrates with models like LLaVA and ChatGPT to provide intelligent insights. It can summarize data, detect anomalies, and generate alerts based on predefined rules.

- **Auto-captioning**: Automatically generates concise and informative captions for images and videos, providing quick insights into the content.

- **Auto-summarization**: Summarizes data from multiple sources into a coherent and concise format, highlighting the most important information.

- **Customizable Configuration**: Easily configure different data sources and processing rules through the user-friendly interface. Glimpser’s configuration is fully database-driven, ensuring flexibility and ease of use.

- **Data Retention Policies**: Automatically manages storage by cleaning up old data, ensuring the system remains efficient without requiring constant manual intervention.

- **Web Interface**: A user-friendly web interface allows for easy monitoring and configuration. Users can view live feeds, summaries, and configure settings without delving into the code.

## Installation

### Prerequisites
- Python 3.8 or higher

### Steps
1. **Clone the Repository**
    ```sh
    git clone https://github.com/yourusername/glimpser.git
    cd glimpser
    ```

2. **Install Dependencies**
    ```sh
    pip install -r requirements.txt
    ```

3. **Run the Application**
    ```sh
    python3 main.py
    ```

You will be prompted to create a secret key to initialize the local sqlite database.  Follow the rest of the guided setup and then direct your browser to http://127.0.0.1:8082 to finish the rest of the setup. 

## Usage

### Configuration
Glimpser uses a database-driven configuration to manage data sources and processing rules. Users can easily add, update, or remove configurations through the web interface.

### Capturing Screenshots
The preferred method for capturing screenshots is through the Glimpser web interface. Simply navigate to the capture section, select your desired source, and click the capture button. This ensures a seamless and user-friendly experience.

### Running Tests
To ensure everything works as expected, you can run the included unit tests:
```sh
python -m unittest discover tests
```

### Motion Detection
Glimpser automatically detects motion in the captured images and videos. When motion is detected, the system can trigger alerts, capture additional data, and generate relevant summaries and captions.

### Auto-captioning
Using advanced AI models, Glimpser generates concise and informative captions for images and videos. This feature helps users quickly understand the content and context of the captured data.

### Auto-summarization
Glimpser can summarize data from multiple sources into a coherent and concise format. The summaries highlight the most important information, making it easier for users to stay informed.

## Contributing
Contributions are always welcome. If you have an idea to improve Glimpser, feel free to fork the repository and submit a pull request. 

### Steps to Contribute
1. Fork the repository.
2. Create a feature branch.
    ```sh
    git checkout -b feature-branch
    ```
3. Commit your changes.
    ```sh
    git commit -m "Description of changes"
    ```
4. Push to the branch.
    ```sh
    git push origin feature-branch
    ```
5. Open a pull request.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgements
We are grateful to the contributors and the open-source community. Special thanks to OpenAI for their powerful models that enable Glimpser's advanced features.
