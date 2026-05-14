// minigame: hungrytotem
#include "minigame_defs.h"

typedef enum gameStates {
    GAMESTATE_INIT,
    GAMESTATE_TITLE,
    GAMESTATE_NORMAL,
    GAMESTATE_EATEN,
    GAMESTATE_WIN,
} gameStates;

typedef enum tileState {
    TILESTATE_EMPTY,
    TILESTATE_ROCK,
    TILESTATE_BOX,
    TILESTATE_TOTEM,
    TILESTATE_PLAYER,
} tileState;

typedef enum direction {
    DIRECTION_NONE,
    DIRECTION_UP,
    DIRECTION_LEFT,
    DIRECTION_RIGHT,
    DIRECTION_DOWN,
} direction;

typedef struct TileStruct {
    tileState state;
    unsigned int pathfind;
} TileStruct;


#define GRID_DIMENSIONS 25
#define BOXES 60
#define ROCKS 30
ROM_DATA static gameStates game_state = GAMESTATE_INIT;
ROM_DATA static TileStruct tiles[GRID_DIMENSIONS][GRID_DIMENSIONS] = {};
ROM_DATA static char change_slot = 0;
ROM_DATA static int player_x = 3;
ROM_DATA static int player_y = 3;
ROM_DATA static int totem_x = 21;
ROM_DATA static int totem_y = 21;
ROM_DATA static int debug = 0;
ROM_DATA static unsigned char ending_timer = 0;
ROM_RODATA_NUM static const rgb game_colors[] = {
    { .red = 0xC0, .green = 0xC0, .blue = 0xC0 }, // TILESTATE_EMPTY,
    { .red = 0x80, .green = 0x80, .blue = 0x80 }, // TILESTATE_ROCK,
    { .red = 0xFF, .green = 0xFF, .blue = 0x00 }, // TILESTATE_BOX,
    { .red = 0xFF, .green = 0x00, .blue = 0x00 }, // TILESTATE_TOTEM,
    { .red = 0x00, .green = 0xFF, .blue = 0x00 }, // TILESTATE_PLAYER,
};
ROM_RODATA_NUM static const char title_text[] = "H\0U\0N\0G\0R\0Y\0 \0T\0O\0T\0E\0M\0";
ROM_RODATA_NUM static const char title_subtext[] = "P\0L\0A\0Y\0";
ROM_RODATA_NUM static const char title_subtext2[] = "E\0X\0I\0T\0";
ROM_DATA static unsigned char frame_timer = 0;
ROM_DATA static unsigned short second_timer = 0;

void placeBox(void) {
    while (1) {
        int x = ((getRNGLower31() >> 10) & 0xFF) % GRID_DIMENSIONS;
        int y = ((getRNGLower31() >> 10) & 0xFF) % GRID_DIMENSIONS;
        if (tiles[x][y].state == TILESTATE_EMPTY) {
            tiles[x][y].state = TILESTATE_BOX;
            return;
        }
    }
}

void placeRock(void) {
    while (1) {
        int x = ((getRNGLower31() >> 10) & 0xFF) % GRID_DIMENSIONS;
        int y = ((getRNGLower31() >> 10) & 0xFF) % GRID_DIMENSIONS;
        if (tiles[x][y].state == TILESTATE_EMPTY) {
            tiles[x][y].state = TILESTATE_ROCK;
            return;
        }
    }
}

void resetGame(void) {
    frame_timer = 0;
    second_timer = 0;
}

void generateBoard(void) {
    for (int x = 0; x < GRID_DIMENSIONS; x++) {
        for (int y = 0; y < GRID_DIMENSIONS; y++) {
            TileStruct *tile = &tiles[x][y];
            tile->state = TILESTATE_EMPTY;
        }
    }
    TileStruct *tile = &tiles[3][3];
    tile->state = TILESTATE_PLAYER;
    tile = &tiles[GRID_DIMENSIONS - 4][GRID_DIMENSIONS - 4];
    tile->state = TILESTATE_TOTEM;
    for (int i = 0; i < BOXES; i++) {
        placeBox();
    }
    for (int i = 0; i < ROCKS; i++) {
        placeRock();
    }

}

#define BOX_DIM 8
#define BOX_BORDER 1
#define X_START (160 - (((float)(GRID_DIMENSIONS) / 2) * BOX_DIM))
#define Y_START (120 - (((float)(GRID_DIMENSIONS) / 2) * BOX_DIM))

int getXStart(int dimension) {
    return 160 - (((float)(dimension) / 2) * BOX_DIM);
}

int getYStart(int dimension) {
    return 120 - (((float)(dimension) / 2) * BOX_DIM);
}

void renderBoard(Gfx **dl_ptr, int show_progress, int dimension_override) {
    const rgb *color = 0;
    int x0 = 0;
    int y0 = 0;
    TileStruct *tile = 0;
    
    Gfx *dl = *dl_ptr;

    // Process
    int dim = GRID_DIMENSIONS;
    if (dimension_override != 0) {
        dim = dimension_override;
    }
    int x_start = getXStart(dim);
    int y_start = getYStart(dim);
    for (int x = 0; x < dim; x++) {
        for (int y = 0; y < dim; y++) {
            if(show_progress){
                x0 = x_start + (x * BOX_DIM);
                y0 = y_start + (y * BOX_DIM);
                // Center
                tile = &tiles[x][y];
                tileState cstate = tile->state;
                color = &game_colors[cstate];
                dl = setFillColor(dl, color->red, color->green, color->blue);
                gDPSetCycleType(dl++, G_CYC_FILL);
                gDPFillRectangle(dl++, x0 + BOX_BORDER, y0 + BOX_BORDER, x0 + (BOX_DIM - BOX_BORDER), y0 + (BOX_DIM - BOX_BORDER));
            }
        }
    }
    *dl_ptr = dl;
}

void handleState_init(Gfx **dl_ptr) {
    Gfx *dl = *dl_ptr;
    game_state = GAMESTATE_TITLE;
    gameInit();
    *dl_ptr = dl;
}

void handleState_title(Gfx **dl_ptr) {
    Gfx *dl = *dl_ptr;
    renderBoard(&dl, 0, 11);
    int x_start = getXStart(11);
    int y_start = getYStart(11);
    for (int i = 0; i < 12; i++) {
        int x0 = x_start + (i * BOX_DIM) + 6;
        int y0 = y_start + (5 * BOX_DIM) + 6;
        int index = i & 5;
        const rgb *color = &game_colors[TILESTATE_BOX + index];
        renderText(&dl, x0, y0, color->red, color->green, color->blue, 0xFF, &title_text[i << 1]);
        if (i == 3) {
            // Start
	        gDPSetPrimColor(dl++, 0, 0, 0xFF, 0xFF, 0xFF, 0xFF);
            gSPTexture(dl++, 0xFFFF, 0xFFFF, 0, G_TX_RENDERTILE, G_ON);
            gDPSetTexturePersp(dl++, G_TP_NONE);
            dl = printText(dl, (x0 + 6) << 2, ((y0 - 2) + BOX_DIM) << 2, 0.65f, "g");
            // B Button
	        gDPSetPrimColor(dl++, 0, 0, 0xFF, 0xFF, 0xFF, 0xFF);
            gSPTexture(dl++, 0xFFFF, 0xFFFF, 0, G_TX_RENDERTILE, G_ON);
            gDPSetTexturePersp(dl++, G_TP_NONE);
            dl = printText(dl, (x0 + 6) << 2, ((y0 - 2) + (2 * BOX_DIM)) << 2, 0.65f, "b");
        } else if ((i > 3) && (i < 8)) {
            color = &game_colors[TILESTATE_BOX + (7 - index)];
            renderText(&dl, x0, y0 + BOX_DIM, color->red, color->green, color->blue, 0xFF, &title_subtext[(i - 4) << 1]);
            color = &game_colors[TILESTATE_BOX + (index - 2)];
            renderText(&dl, x0, y0 + (2 * BOX_DIM), color->red, color->green, color->blue, 0xFF, &title_subtext2[(i - 4) << 1]);
        }
    }
    if (p1PressedButtons & START_BUTTON) {
        resetGame();
        generateBoard();
        game_state = GAMESTATE_NORMAL;
    } else if (p1PressedButtons & B_BUTTON) {
        gameExit();
    }
    *dl_ptr = dl;
}

char moveBox(int x, int y, direction boxdir){
    if(tiles[x][y].state != TILESTATE_BOX && tiles[x][y].state != TILESTATE_PLAYER){
        return 0;
    }
    switch(boxdir){
        case DIRECTION_UP:
            if(y > 0){
                if(tiles[x][y - 1].state == TILESTATE_EMPTY || moveBox(x, y - 1, boxdir)){
                    tiles[x][y].state = TILESTATE_EMPTY;
                    tiles[x][y - 1].state = TILESTATE_BOX;
                    return 1;
                }
            }
            return 0;
            break;
        case DIRECTION_LEFT:
            if(x > 0){
                if(tiles[x - 1][y].state == TILESTATE_EMPTY || moveBox(x - 1, y, boxdir)){
                    tiles[x][y].state = TILESTATE_EMPTY;
                    tiles[x - 1][y].state = TILESTATE_BOX;
                    return 1;
                }
            }
            return 0;
            break;
        case DIRECTION_RIGHT:
            if(x < (GRID_DIMENSIONS - 1)){
                if(tiles[x + 1][y].state == TILESTATE_EMPTY || moveBox(x + 1, y, boxdir)){
                    tiles[x][y].state = TILESTATE_EMPTY;
                    tiles[x + 1][y].state = TILESTATE_BOX;
                    return 1;
                }
            }
            return 0;
            break;
        case DIRECTION_DOWN:
            if(y < (GRID_DIMENSIONS - 1)){
                if(tiles[x][y + 1].state == TILESTATE_EMPTY || moveBox(x, y + 1, boxdir)){
                    tiles[x][y].state = TILESTATE_EMPTY;
                    tiles[x][y + 1].state = TILESTATE_BOX;
                    return 1;
                }
            }
            return 0;
            break;
        case DIRECTION_NONE:
            return tiles[x][y].state == TILESTATE_EMPTY;
            break;
        default:
            return 0;
            break;
    }
}

void defeat(){
    game_state = GAMESTATE_EATEN;
    ending_timer = 120;
    playSFXWrapper(246);
}

void moveTotem(direction totdir){
    tiles[totem_x][totem_y].state = TILESTATE_EMPTY;
    switch(totdir){
        case DIRECTION_UP:
            tiles[totem_x][totem_y - 1].state = TILESTATE_TOTEM;
            totem_y--;
            if(tiles[totem_x][totem_y - 1].state == TILESTATE_PLAYER){
                defeat();
            }
            break;
        case DIRECTION_LEFT:
            tiles[totem_x - 1][totem_y].state = TILESTATE_TOTEM;
            totem_x--;
            if(tiles[totem_x - 1][totem_y].state == TILESTATE_PLAYER){
                defeat();
            }
            break;
        case DIRECTION_RIGHT:
            tiles[totem_x + 1][totem_y].state = TILESTATE_TOTEM;
            totem_x++;
            if(tiles[totem_x + 1][totem_y].state == TILESTATE_PLAYER){
                defeat();
            }
            break;
        case DIRECTION_DOWN:
            tiles[totem_x][totem_y + 1].state = TILESTATE_TOTEM;
            totem_y++;
            if(tiles[totem_x][totem_y + 1].state == TILESTATE_PLAYER){
                defeat();
            }
            break;
        case DIRECTION_NONE:
            return;
            break;
        default:
            return;
            break;
    }
    return;
}

tileState checkFieldState(int x, int y, direction dir){
    switch(dir){
        case DIRECTION_UP:
            if(y > 0){
                return tiles[x][y - 1].state;
            } else {
                return TILESTATE_ROCK;
            }
            break;
        case DIRECTION_LEFT:
            if(x > 0){
                return tiles[x - 1][y].state;
            } else {
                return TILESTATE_ROCK;
            }
            break;
        case DIRECTION_RIGHT:
            if(x < (GRID_DIMENSIONS - 1)){
                return tiles[x + 1][y].state;
            } else {
                return TILESTATE_ROCK;
            }
            break;
        case DIRECTION_DOWN:
            if(y < (GRID_DIMENSIONS - 1)){
                return tiles[x][y + 1].state;
            } else {
                return TILESTATE_ROCK;
            }
            break;
        case DIRECTION_NONE:
            return tiles[x][y].state;
            break;
        default:
            return TILESTATE_ROCK;
            break;
    }
}

tileState checkFieldPathing(int x, int y, direction dir){
    switch(dir){
        case DIRECTION_UP:
            if(y > 0){
                return tiles[x][y - 1].pathfind;
            } else {
                return 9000;
            }
            break;
        case DIRECTION_LEFT:
            if(x > 0){
                return tiles[x - 1][y].pathfind;
            } else {
                return 9000;
            }
            break;
        case DIRECTION_RIGHT:
            if(x < (GRID_DIMENSIONS - 1)){
                return tiles[x + 1][y].pathfind;
            } else {
                return 9000;
            }
            break;
        case DIRECTION_DOWN:
            if(y < (GRID_DIMENSIONS - 1)){
                return tiles[x][y + 1].pathfind;
            } else {
                return 9000;
            }
            break;
        case DIRECTION_NONE:
            return tiles[x][y].pathfind;
            break;
        default:
            return 9000;
            break;
    }
}

void seek(int x, int y, unsigned int distance){
    if(x < 0 || y < 0){
        return;
    }
    if(x >= GRID_DIMENSIONS || y >= GRID_DIMENSIONS){
        return;
    }
    if(checkFieldPathing(x, y, DIRECTION_NONE) > distance){
        tiles[x][y].pathfind = distance;
    }
    if(checkFieldState(x, y, DIRECTION_UP) == TILESTATE_EMPTY && checkFieldPathing(x, y, DIRECTION_UP) == 9000){
        seek(x, (y - 1), (distance + 1));
    }
    if(checkFieldState(x, y, DIRECTION_LEFT) == TILESTATE_EMPTY && checkFieldPathing(x, y, DIRECTION_LEFT) == 9000){
        seek((x - 1), y, (distance + 1));
    }
    if(checkFieldState(x, y, DIRECTION_RIGHT) == TILESTATE_EMPTY && checkFieldPathing(x, y, DIRECTION_RIGHT) == 9000){
        seek((x + 1), y, (distance + 1));
    }
    if(checkFieldState(x, y, DIRECTION_DOWN) == TILESTATE_EMPTY && checkFieldPathing(x, y, DIRECTION_DOWN) == 9000){
        seek(x, (y + 1), (distance + 1));
    }
}

void pathFind(){
    debug = 177;
    direction shortest = DIRECTION_NONE;
    unsigned int lowestValue = 9000;
    for (int x = 0; x < GRID_DIMENSIONS; x++) {
        for (int y = 0; y < GRID_DIMENSIONS; y++) {
            TileStruct *tile = &tiles[x][y];
            tile->pathfind = 9000;
        }
    }
    seek(player_x, player_y, 0);
    debug = 178;
    
    if(checkFieldPathing(totem_x, totem_y, DIRECTION_UP) < lowestValue){
        shortest = DIRECTION_UP;
        lowestValue = checkFieldPathing(totem_x, totem_y, DIRECTION_UP);
    }
    if(checkFieldPathing(totem_x, totem_y, DIRECTION_LEFT) < lowestValue){
        shortest = DIRECTION_LEFT;
        lowestValue = checkFieldPathing(totem_x, totem_y, DIRECTION_LEFT);
    }
    if(checkFieldPathing(totem_x, totem_y, DIRECTION_RIGHT) < lowestValue){
        shortest = DIRECTION_RIGHT;
        lowestValue = checkFieldPathing(totem_x, totem_y, DIRECTION_RIGHT);
    }
    if(checkFieldPathing(totem_x, totem_y, DIRECTION_DOWN) < lowestValue){
        shortest = DIRECTION_DOWN;
        lowestValue = checkFieldPathing(totem_x, totem_y, DIRECTION_DOWN);
    }

    if(shortest != DIRECTION_NONE){
        debug = 179;
        moveTotem(shortest);
        debug = 180;
    } else {
        game_state = GAMESTATE_WIN;
        playSFXWrapper(71);
        ending_timer = 180;
    }
}

void movePlayer(void) {
    direction movdir = DIRECTION_NONE;
    if (change_slot == 1) {
        change_slot = 2;
    }
    if ((MinigameInput->stickX < -0x20) || MinigameInput->Buttons.d_left) {
        if (change_slot == 0) {
            movdir = DIRECTION_LEFT;
        }
    } else if ((MinigameInput->stickX > 0x20) || MinigameInput->Buttons.d_right) {
        if (change_slot == 0) {
            movdir = DIRECTION_RIGHT;
        }
    } else if ((MinigameInput->stickY > 0x20) || MinigameInput->Buttons.d_up) {
        if (change_slot == 0) {
            movdir = DIRECTION_UP;
        }
    } else if ((MinigameInput->stickY < -0x20) || MinigameInput->Buttons.d_down) {
        if (change_slot == 0) {
            movdir = DIRECTION_DOWN;
        }
    } else {
        change_slot = 0;
    }
    if(movdir != DIRECTION_NONE){
        if(checkFieldState(player_x, player_y, movdir) == TILESTATE_EMPTY || moveBox(player_x, player_y, movdir)){
            tiles[player_x][player_y].state = TILESTATE_EMPTY;
            if(movdir == DIRECTION_UP){
                tiles[player_x][(player_y - 1)].state = TILESTATE_PLAYER;
                player_y--;
            } else if(movdir == DIRECTION_LEFT){
                tiles[(player_x - 1)][player_y].state = TILESTATE_PLAYER;
                player_x--;
            } else if(movdir == DIRECTION_RIGHT){
                tiles[(player_x + 1)][player_y].state = TILESTATE_PLAYER;
                player_x++;
            } else if(movdir == DIRECTION_DOWN){
                tiles[player_x][(player_y + 1)].state = TILESTATE_PLAYER;
                player_y++;
            }
        }
        change_slot = 1;
    }
}

void handleState_normal(Gfx **dl_ptr, gameStates state) {
    Gfx *dl = *dl_ptr;
    if (state == GAMESTATE_NORMAL) {
        // Controls
        movePlayer();
        frame_timer++;
        if (frame_timer > 47) {
            frame_timer = 0;
            pathFind();
        }
    } else if (state == GAMESTATE_EATEN) {
        if (ending_timer > 0) {
            ending_timer--;
            if (ending_timer == 0) {
                game_state = GAMESTATE_TITLE;
            }
        }
    } else if (state == GAMESTATE_WIN) {
        if (ending_timer > 0) {
            ending_timer--;
            if (ending_timer == 0) {
                gameVictory();
            }
        }
    }
    renderBoard(&dl, 1, 0);
    *dl_ptr = dl;
}

void loop(Gfx **dl_ptr) {
    Gfx *dl = *dl_ptr;
    if (game_state != GAMESTATE_INIT) {
        dl = minigame_dl_init(dl, 1, 0x80, 0x80, 0x80);
    }
    switch(game_state) {
        case GAMESTATE_INIT:
            handleState_init(&dl);
            debug = 170;
            tiles[0][0].pathfind = 48; // debug code
            break;
        case GAMESTATE_TITLE:
            handleState_title(&dl);
            break;
        case GAMESTATE_NORMAL:
        case GAMESTATE_EATEN:
        case GAMESTATE_WIN:
            handleState_normal(&dl, game_state);
            break;
        default:
            break;
    }
    *dl_ptr = dl;
}