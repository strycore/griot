//! griot face — a subtitle-style status window for the voice loop.
//!
//! Binds a unix socket and renders state pushed by `converse.py`:
//!   * a big emoji — the thinking emoji while busy, otherwise the model's
//!     chosen expression
//!   * two subtitle lines — what it heard (🎙) and what it's saying (🔊)
//!
//! Protocol: newline-delimited JSON, each line a partial update that is merged
//! into the current state: {"busy":true} {"emoji":"😎"} {"heard":"..."} {"saying":"..."}

use futures::Stream;
use iced::widget::{column, container, row, text};
use iced::{Center, Color, Element, Fill, Font, Subscription, Theme};
use serde::Deserialize;
use tokio::io::AsyncBufReadExt;

const THINKING: &str = "🤔";
const DEFAULT_EMOJI: &str = "🤖";
// iced doesn't fall back to system fonts or render colour emoji, so we bundle a
// monochrome emoji font and apply it explicitly to every emoji glyph.
const EMOJI_FONT: Font = Font::with_name("Noto Emoji");
const EMOJI_TTF: &[u8] = include_bytes!("../fonts/NotoEmoji-Regular.ttf");

fn sock_path() -> std::path::PathBuf {
    let dir = std::env::var("XDG_RUNTIME_DIR").unwrap_or_else(|_| "/tmp".into());
    std::path::Path::new(&dir).join("griot-face.sock")
}

#[derive(Debug, Clone, Deserialize)]
struct Patch {
    #[serde(default)]
    emoji: Option<String>,
    #[serde(default)]
    busy: Option<bool>,
    #[serde(default)]
    heard: Option<String>,
    #[serde(default)]
    saying: Option<String>,
}

#[derive(Debug, Clone)]
enum Message {
    State(Patch),
}

struct Face {
    emoji: String,
    busy: bool,
    heard: String,
    saying: String,
}

impl Default for Face {
    fn default() -> Self {
        Self {
            emoji: DEFAULT_EMOJI.to_string(),
            busy: false,
            heard: String::new(),
            saying: String::new(),
        }
    }
}

fn update(state: &mut Face, message: Message) {
    let Message::State(p) = message;
    if let Some(e) = p.emoji {
        if !e.is_empty() {
            state.emoji = e;
        }
    }
    if let Some(b) = p.busy {
        state.busy = b;
    }
    if let Some(h) = p.heard {
        state.heard = h;
    }
    if let Some(s) = p.saying {
        state.saying = s;
    }
}

fn view(state: &Face) -> Element<Message> {
    let face = if state.busy { THINKING } else { state.emoji.as_str() };

    let dim = Color::from_rgb(0.55, 0.57, 0.62);
    let bright = Color::from_rgb(0.95, 0.96, 1.0);

    let big = text(face).font(EMOJI_FONT).size(140);
    let heard = subtitle("🎙", &state.heard, 22, dim);
    let saying = subtitle("🔊", &state.saying, 28, bright);

    let body = column![big, heard, saying].spacing(14).align_x(Center);

    container(body)
        .center_x(Fill)
        .center_y(Fill)
        .padding(24)
        .into()
}

/// One subtitle line: an emoji-font icon next to plain text. Empty when blank so
/// the layout doesn't show a lone icon.
fn subtitle<'a>(icon: &'a str, content: &str, size: u16, color: Color) -> Element<'a, Message> {
    if content.is_empty() {
        return text("").size(size).into();
    }
    row![
        text(icon).font(EMOJI_FONT).size(size - 6).color(color),
        text(content.to_string()).size(size).color(color),
    ]
    .spacing(10)
    .align_y(Center)
    .into()
}

fn subscription(_: &Face) -> Subscription<Message> {
    Subscription::run(socket_stream)
}

/// Bind the socket, accept connections, and yield each JSON line as a Message.
/// Survives the client (the voice loop) disconnecting and reconnecting.
fn socket_stream() -> impl Stream<Item = Message> {
    async_stream::stream! {
        let path = sock_path();
        let _ = std::fs::remove_file(&path);
        let listener = match tokio::net::UnixListener::bind(&path) {
            Ok(l) => l,
            Err(e) => {
                eprintln!("face: cannot bind {path:?}: {e}");
                return;
            }
        };
        eprintln!("face: listening on {path:?}");
        loop {
            if let Ok((stream, _)) = listener.accept().await {
                let mut lines = tokio::io::BufReader::new(stream).lines();
                while let Ok(Some(line)) = lines.next_line().await {
                    if let Ok(patch) = serde_json::from_str::<Patch>(&line) {
                        yield Message::State(patch);
                    }
                }
            }
        }
    }
}

fn main() -> iced::Result {
    iced::application("griot", update, view)
        .subscription(subscription)
        .font(EMOJI_TTF)
        .theme(|_| Theme::Dark)
        .window_size(iced::Size::new(780.0, 340.0))
        .run()
}
